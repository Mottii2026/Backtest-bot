import os
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application, CommandHandler,
    ContextTypes,
)
import gspread
from google.oauth2.service_account import Credentials
import json

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

def get_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    return client.open_by_key(sheet_id)

def get_ws(name, headers):
    ss = get_sheet()
    try:
        return ss.worksheet(name)
    except:
        ws = ss.add_worksheet(name, rows=1000, cols=15)
        ws.append_row(headers)
        return ws

def get_islemler():
    return get_ws("İşlemler", ["ID","Hisse","Tip","Tarih","Fiyat","Lot","Toplam","KapFiyat","KapLot","KZTL","KZPct","Not"])

def get_ayarlar():
    return get_ws("Ayarlar", ["Parametre","Deger"])
def get_ayar(p):
    ws = get_ayarlar()
    rows = ws.get_all_records()
    defaults = {"Ana Para":100000,"Stop %":10,"TP1 %":8,"TP2 %":15,"TP3 %":30}
    for r in rows:
        if r.get("Parametre")==p:
            return float(r.get("Deger",0))
    return defaults.get(p,0)

def set_ayar(p,v):
    ws = get_ayarlar()
    cell = ws.find(p)
    if cell:
        ws.update_cell(cell.row,2,str(v))
    else:
        ws.append_row([p,str(v)])

def hesapla(hisse):
    ws = get_islemler()
    rows = [r for r in ws.get_all_records() if r.get("Hisse","").upper()==hisse.upper()]
    alis_lot=0
    alis_maliyet=0
    for r in rows:
        t=r.get("Tip","").upper()
        if t in ["LONG","DCA1","DCA2","DCA3"]:
            f=float(r.get("Fiyat",0) or 0)
            l=float(r.get("Lot",0) or 0)
            alis_lot+=l
            alis_maliyet+=f*l
    if alis_lot==0:
        return 0,0,0
    ort=alis_maliyet/alis_lot
    satilan=sum(float(r.get("KapLot",0) or 0) for r in rows if r.get("Tip","").upper() in ["TP1","TP2","TP3","BE","STOP"])
    acik=alis_lot-satilan
    return ort,acik,ort*acik

def ana_para():
    ws=get_islemler()
    rows=ws.get_all_records()
    kz=sum(float(r.get("KZTL",0) or 0) for r in rows)
    return get_ayar("Ana Para")+kz

def yeni_id():
    ws=get_islemler()
    rows=ws.get_all_records()
    ids=[int(r.get("ID",0) or 0) for r in rows if r.get("ID")]
    return max(ids)+1 if ids else 1

def fp(n):
    try: return f"{float(n):,.2f} ₺"
    except: return "0,00 ₺"

def fn(n,d=2):
    try: return f"{float(n):,.{d}f}"
    except: return "0"

def hedefler(ort):
    sp=get_ayar("Stop %")
    t1=get_ayar("TP1 %")
    t2=get_ayar("TP2 %")
    t3=get_ayar("TP3 %")
    return {
        "stop":ort*(1-sp/100),"be":ort,
        "tp1":ort*(1+t1/100),"tp2":ort*(1+t2/100),"tp3":ort*(1+t3/100),
        "sp":sp,"t1":t1,"t2":t2,"t3":t3
    }
  async def start(update,context):
    msg=(
        "📊 *BACKTEST BOT*\n\n"
        "📥 *ALIŞ*\n"
        "`/long HISSE FIYAT LOT`\n"
        "`/dca1 HISSE FIYAT LOT`\n"
        "`/dca2 HISSE FIYAT LOT`\n"
        "`/dca3 HISSE FIYAT LOT`\n\n"
        "📤 *KAPANIS*\n"
        "`/tp1 HISSE FIYAT LOT`\n"
        "`/tp2 HISSE FIYAT LOT`\n"
        "`/tp3 HISSE FIYAT LOT`\n"
        "`/be HISSE FIYAT LOT`\n"
        "`/stop HISSE FIYAT LOT`\n\n"
        "📊 *SORGULAMA*\n"
        "`/durum HISSE`\n"
        "`/ozet`\n"
        "`/stats`\n\n"
        "⚙️ *AYARLAR*\n"
        "`/ayarlar`\n"
        "`/set stop 10`\n"
        "`/set tp1 8`\n"
        "`/set tp2 15`\n"
        "`/set tp3 30`\n"
        "`/set para 100000`\n\n"
        "💡 *Örnek:* `/long RYGYO 22.50 5000`"
    )
    await update.message.reply_text(msg,parse_mode="Markdown")

async def alis(update,context,tip):
    args=context.args
    if len(args)<3:
        await update.message.reply_text(f"❌ Kullanım: `/{tip.lower()} HISSE FIYAT LOT`",parse_mode="Markdown")
        return
    hisse=args[0].upper()
    try:
        fiyat=float(args[1].replace(",","."))
        lot=float(args[2].replace(",","."))
    except:
        await update.message.reply_text("❌ Fiyat ve lot sayı olmalı!")
        return
    toplam=fiyat*lot
    tarih=datetime.now().strftime("%d.%m.%Y %H:%M")
    ws=get_islemler()
    nid=yeni_id()
    ws.append_row([nid,hisse,tip.upper(),tarih,fiyat,lot,toplam,"","","","",""])
    ort,acik,acik_m=hesapla(hisse)
    h=hedefler(ort)
    msg=(
        f"🟢 *{hisse} — {tip.upper()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Fiyat: `{fn(fiyat)}` | Lot: `{fn(lot,0)}`\n"
        f"💵 Toplam: `{fp(toplam)}`\n"
        f"📊 Ortalama: `{fn(ort)}`\n"
        f"📦 Açık Lot: `{fn(acik,0)}`\n\n"
        f"🎯 *HEDEFLER:*\n"
        f"🔴 STOP (%{h['sp']}): `{fn(h['stop'])}`\n"
        f"⚪ BE: `{fn(h['be'])}`\n"
        f"🟢 TP1 (%{h['t1']}): `{fn(h['tp1'])}`\n"
        f"🟢 TP2 (%{h['t2']}): `{fn(h['tp2'])}`\n"
        f"🟢 TP3 (%{h['t3']}): `{fn(h['tp3'])}`\n\n"
        f"💳 Ana Para: `{fp(ana_para())}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Kaydedildi (#{nid})"
    )
    await update.message.reply_text(msg,parse_mode="Markdown")

async def long_cmd(u,c): await alis(u,c,"LONG")
async def dca1_cmd(u,c): await alis(u,c,"DCA1")
async def dca2_cmd(u,c): await alis(u,c,"DCA2")
async def dca3_cmd(u,c): await alis(u,c,"DCA3")
async def kapanis(update,context,tip):
    args=context.args
    if len(args)<3:
        await update.message.reply_text(f"❌ Kullanım: `/{tip.lower()} HISSE FIYAT LOT`",parse_mode="Markdown")
        return
    hisse=args[0].upper()
    try:
        kfiyat=float(args[1].replace(",","."))
        klot=float(args[2].replace(",","."))
    except:
        await update.message.reply_text("❌ Fiyat ve lot sayı olmalı!")
        return
    ort,acik,acik_m=hesapla(hisse)
    if ort==0:
        await update.message.reply_text(f"❌ *{hisse}* için açık pozisyon yok!",parse_mode="Markdown")
        return
    if klot>acik:
        await update.message.reply_text(f"❌ Kapanacak lot ({fn(klot,0)}) açık lottan ({fn(acik,0)}) fazla!")
        return
    kz_tl=(kfiyat-ort)*klot
    kz_pct=((kfiyat/ort)-1)*100
    tarih=datetime.now().strftime("%d.%m.%Y %H:%M")
    ws=get_islemler()
    nid=yeni_id()
    ws.append_row([nid,hisse,tip.upper(),tarih,"","","",kfiyat,klot,round(kz_tl,2),round(kz_pct,2),""])
    yort,yacik,yacik_m=hesapla(hisse)
    ap=ana_para()
    emojiler={"TP1":"🎯","TP2":"🎯🎯","TP3":"🎯🎯🎯","BE":"⚪","STOP":"🛑"}
    e=emojiler.get(tip.upper(),"📤")
    ke="🟢" if kz_tl>=0 else "🔴"
    msg=(
        f"{e} *{hisse} — {tip.upper()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Ortalama: `{fn(ort)}`\n"
        f"💰 Kapanış: `{fn(kfiyat)}` | Lot: `{fn(klot,0)}`\n\n"
        f"{ke} *KÂR/ZARAR:*\n"
        f"   TL: `{fp(kz_tl)}`\n"
        f"   %: `{kz_pct:+.2f}%`\n\n"
    )
    if yacik>0:
        h=hedefler(yort)
        msg+=(
            f"📦 Kalan Lot: `{fn(yacik,0)}`\n"
            f"🔴 STOP: `{fn(h['stop'])}` | 🟢 TP1: `{fn(h['tp1'])}`\n\n"
        )
    else:
        msg+="✅ Pozisyon tamamen kapandı!\n\n"
    msg+=(
        f"💳 Ana Para: `{fp(ap)}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Kaydedildi (#{nid})"
    )
    await update.message.reply_text(msg,parse_mode="Markdown")

async def tp1_cmd(u,c): await kapanis(u,c,"TP1")
async def tp2_cmd(u,c): await kapanis(u,c,"TP2")
async def tp3_cmd(u,c): await kapanis(u,c,"TP3")
async def be_cmd(u,c): await kapanis(u,c,"BE")
async def stop_cmd(u,c): await kapanis(u,c,"STOP")
async def durum_cmd(update,context):
    if not context.args:
        await update.message.reply_text("❌ Kullanım: `/durum HISSE`",parse_mode="Markdown")
        return
    hisse=context.args[0].upper()
    ort,acik,acik_m=hesapla(hisse)
    if ort==0:
        await update.message.reply_text(f"❌ *{hisse}* bulunamadı!",parse_mode="Markdown")
        return
    h=hedefler(ort)
    durum="🟢 AÇIK" if acik>0 else "⚫ KAPALI"
    msg=(
        f"📊 *{hisse} — DURUM*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 {durum}\n"
        f"📊 Ortalama: `{fn(ort)}`\n"
        f"📦 Açık Lot: `{fn(acik,0)}`\n"
        f"💼 Açık Poz.: `{fp(acik_m)}`\n\n"
        f"🎯 *HEDEFLER:*\n"
        f"🔴 STOP (%{h['sp']}): `{fn(h['stop'])}`\n"
        f"⚪ BE: `{fn(h['be'])}`\n"
        f"🟢 TP1 (%{h['t1']}): `{fn(h['tp1'])}`\n"
        f"🟢 TP2 (%{h['t2']}): `{fn(h['tp2'])}`\n"
        f"🟢 TP3 (%{h['t3']}): `{fn(h['tp3'])}`"
    )
    await update.message.reply_text(msg,parse_mode="Markdown")

async def ozet_cmd(update,context):
    ws=get_islemler()
    rows=ws.get_all_records()
    if not rows:
        await update.message.reply_text("📭 Henüz işlem yok!")
        return
    hisseler=list(set(r.get("Hisse","") for r in rows if r.get("Hisse")))
    ap_bas=get_ayar("Ana Para")
    kz=sum(float(r.get("KZTL",0) or 0) for r in rows)
    msg=(
        f"💼 *PORTFÖY*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Başlangıç: `{fp(ap_bas)}`\n"
        f"💳 Güncel: `{fp(ap_bas+kz)}`\n"
        f"{'🟢' if kz>=0 else '🔴'} Net K/Z: `{fp(kz)}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
    )
    for h in sorted(hisseler):
        ort,acik,acik_m=hesapla(h)
        hkz=sum(float(r.get("KZTL",0) or 0) for r in rows if r.get("Hisse","").upper()==h.upper())
        if acik>0:
            hd=hedefler(ort)
            msg+=f"🟢 *{h}* | Ort:`{fn(ort)}` | Lot:`{fn(acik,0)}`\n🔴`{fn(hd['stop'])}` 🟢`{fn(hd['tp1'])}`\n"
        else:
            msg+=f"⚫ *{h}* {'🟢' if hkz>=0 else '🔴'}`{fp(hkz)}`\n"
    await update.message.reply_text(msg,parse_mode="Markdown")

async def stats_cmd(update,context):
    ws=get_islemler()
    rows=ws.get_all_records()
    krows=[r for r in rows if r.get("Tip","").upper() in ["TP1","TP2","TP3","BE","STOP"]]
    if not krows:
        await update.message.reply_text("📭 Henüz kapanmış işlem yok!")
        return
    kazanli=[r for r in krows if float(r.get("KZTL",0) or 0)>0]
    zarar=[r for r in krows if float(r.get("KZTL",0) or 0)<=0]
    tkz=sum(float(r.get("KZTL",0) or 0) for r in krows)
    ap=get_ayar("Ana Para")
    ko=len(kazanli)/len(krows)*100 if krows else 0
    msg=(
        f"📈 *İSTATİSTİKLER*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 Net K/Z: `{fp(tkz)}` ({tkz/ap*100:+.2f}%)\n"
        f"📊 Toplam işlem: {len(krows)}\n"
        f"🟢 Kârlı: {len(kazanli)} | 🔴 Zararlı: {len(zarar)}\n"
        f"🎯 Kazanma: `{ko:.1f}%`\n"
        f"TP1:{sum(1 for r in krows if r.get('Tip','').upper()=='TP1')} "
        f"TP2:{sum(1 for r in krows if r.get('Tip','').upper()=='TP2')} "
        f"TP3:{sum(1 for r in krows if r.get('Tip','').upper()=='TP3')} "
        f"STOP:{sum(1 for r in krows if r.get('Tip','').upper()=='STOP')}"
    )
    await update.message.reply_text(msg,parse_mode="Markdown")

async def ayarlar_cmd(update,context):
    msg=(
        f"⚙️ *AYARLAR*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Ana Para: `{fp(get_ayar('Ana Para'))}`\n"
        f"🔴 Stop: `{get_ayar('Stop %')}%`\n"
        f"🟢 TP1: `{get_ayar('TP1 %')}%`\n"
        f"🟢 TP2: `{get_ayar('TP2 %')}%`\n"
        f"🟢 TP3: `{get_ayar('TP3 %')}%`"
    )
    await update.message.reply_text(msg,parse_mode="Markdown")

async def set_cmd(update,context):
    pm={"stop":"Stop %","tp1":"TP1 %","tp2":"TP2 %","tp3":"TP3 %","para":"Ana Para"}
    if len(context.args)<2 or context.args[0].lower() not in pm:
        await update.message.reply_text("❌ Kullanım: `/set stop 10`",parse_mode="Markdown")
        return
    try:
        v=float(context.args[1].replace(",","."))
    except:
        await update.message.reply_text("❌ Değer sayı olmalı!")
        return
    p=pm[context.args[0].lower()]
    set_ayar(p,v)
    await update.message.reply_text(f"✅ *{p}* → `{v}` güncellendi!",parse_mode="Markdown")

async def hata(update,context):
    logger.error(f"Hata: {context.error}")

def main():
    token=os.environ.get("TELEGRAM_BOT_TOKEN")
    app=Application.builder().token(token).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("help",start))
    app.add_handler(CommandHandler("long",long_cmd))
    app.add_handler(CommandHandler("dca1",dca1_cmd))
    app.add_handler(CommandHandler("dca2",dca2_cmd))
    app.add_handler(CommandHandler("dca3",dca3_cmd))
    app.add_handler(CommandHandler("tp1",tp1_cmd))
    app.add_handler(CommandHandler("tp2",tp2_cmd))
    app.add_handler(CommandHandler("tp3",tp3_cmd))
    app.add_handler(CommandHandler("be",be_cmd))
    app.add_handler(CommandHandler("stop",stop_cmd))
    app.add_handler(CommandHandler("durum",durum_cmd))
    app.add_handler(CommandHandler("ozet",ozet_cmd))
    app.add_handler(CommandHandler("stats",stats_cmd))
    app.add_handler(CommandHandler("ayarlar",ayarlar_cmd))
    app.add_handler(CommandHandler("set",set_cmd))
    app.add_error_handler(hata)
    logger.info("Bot başlatılıyor...")
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()

