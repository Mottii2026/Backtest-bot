import os,json,logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application,CommandHandler,ContextTypes
import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',level=logging.INFO)
logger=logging.getLogger(__name__)
SCOPES=['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']

def get_sheet():
    creds_dict=json.loads(os.environ.get("GOOGLE_CREDENTIALS_JSON"))
    creds=Credentials.from_service_account_info(creds_dict,scopes=SCOPES)
    client=gspread.authorize(creds)
    return client.open_by_key(os.environ.get("GOOGLE_SHEET_ID"))

def get_ws(name,headers):
    ss=get_sheet()
    try:
        return ss.worksheet(name)
    except:
        ws=ss.add_worksheet(name,rows=1000,cols=15)
        ws.append_row(headers)
        return ws

def get_islemler():
    return get_ws("Islemler",["ID","Hisse","Tip","Tarih","Fiyat","Lot","Toplam","KapFiyat","KapLot","KZTL","KZPct","Not"])

def get_ayarlar():
    return get_ws("Ayarlar",["Parametre","Deger"])

def get_ayar(p):
    defaults={"Ana Para":100000,"Stop":10,"TP1":8,"TP2":15,"TP3":30}
    try:
        rows=get_ayarlar().get_all_records()
        for r in rows:
            if r.get("Parametre")==p:
                return float(r.get("Deger",0))
    except:
        pass
    return defaults.get(p,0)

def set_ayar(p,v):
    ws=get_ayarlar()
    try:
        cell=ws.find(p)
        ws.update_cell(cell.row,2,str(v))
    except:
        ws.append_row([p,str(v)])

def hesapla(hisse):
    try:
        rows=[r for r in get_islemler().get_all_records() if str(r.get("Hisse","")).upper()==hisse.upper()]
    except:
        return 0,0,0
    al=0
    am=0
    for r in rows:
        t=str(r.get("Tip","")).upper()
        if t in ["LONG","DCA1","DCA2","DCA3"]:
            f=float(r.get("Fiyat",0) or 0)
            l=float(r.get("Lot",0) or 0)
            al+=l
            am+=f*l
    if al==0:
        return 0,0,0
    ort=am/al
    sat=sum(float(r.get("KapLot",0) or 0) for r in rows if str(r.get("Tip","")).upper() in ["TP1","TP2","TP3","BE","STOP"])
    acik=al-sat
    return ort,acik,ort*acik

def ana_para():
    try:
        rows=get_islemler().get_all_records()
        kz=sum(float(r.get("KZTL",0) or 0) for r in rows)
        return get_ayar("Ana Para")+kz
    except:
        return get_ayar("Ana Para")

def yeni_id():
    try:
        rows=get_islemler().get_all_records()
        ids=[int(r.get("ID",0) or 0) for r in rows if r.get("ID")]
        return max(ids)+1 if ids else 1
    except:
        return 1

def fp(n):
    try:
        return f"{float(n):,.2f} TL"
    except:
        return "0 TL"

def fn(n,d=2):
    try:
        return f"{float(n):,.{d}f}"
    except:
        return "0"

def h(ort):
    sp=get_ayar("Stop")
    t1=get_ayar("TP1")
    t2=get_ayar("TP2")
    t3=get_ayar("TP3")
    return {"stop":ort*(1-sp/100),"be":ort,"tp1":ort*(1+t1/100),"tp2":ort*(1+t2/100),"tp3":ort*(1+t3/100),"sp":sp,"t1":t1,"t2":t2,"t3":t3}

async def start(update,context):
    msg=("📊 *BACKTEST BOT*\n\n"
"📥 *ALIS*\n"
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
"Ornek: `/long RYGYO 22.50 5000`")
    await update.message.reply_text(msg,parse_mode="Markdown")

async def alis(update,context,tip):
    args=context.args
    if len(args)<3:
        await update.message.reply_text(f"Kullanim: /{tip.lower()} HISSE FIYAT LOT")
        return
    hisse=args[0].upper()
    try:
        fiyat=float(args[1].replace(",","."))
        lot=float(args[2].replace(",","."))
    except:
        await update.message.reply_text("Fiyat ve lot sayi olmali!")
        return
    toplam=fiyat*lot
    tarih=datetime.now().strftime("%d.%m.%Y %H:%M")
    ws=get_islemler()
    nid=yeni_id()
    ws.append_row([nid,hisse,tip.upper(),tarih,fiyat,lot,toplam,"","","","",""])
    ort,acik,acik_m=hesapla(hisse)
    hd=h(ort)
    msg=(f"ALIS: *{hisse} - {tip.upper()}*\n"
f"Fiyat: `{fn(fiyat)}` | Lot: `{fn(lot,0)}`\n"
f"Toplam: `{fp(toplam)}`\n"
f"Ortalama: `{fn(ort)}`\n"
f"Acik Lot: `{fn(acik,0)}`\n\n"
f"HEDEFLER:\n"
f"STOP (%{hd['sp']}): `{fn(hd['stop'])}`\n"
f"BE: `{fn(hd['be'])}`\n"
f"TP1 (%{hd['t1']}): `{fn(hd['tp1'])}`\n"
f"TP2 (%{hd['t2']}): `{fn(hd['tp2'])}`\n"
f"TP3 (%{hd['t3']}): `{fn(hd['tp3'])}`\n\n"
f"Ana Para: `{fp(ana_para())}`\n"
f"Kaydedildi (#{nid})")
    await update.message.reply_text(msg,parse_mode="Markdown")

async def long_cmd(u,c): await alis(u,c,"LONG")
async def dca1_cmd(u,c): await alis(u,c,"DCA1")
async def dca2_cmd(u,c): await alis(u,c,"DCA2")
async def dca3_cmd(u,c): await alis(u,c,"DCA3")

async def kapanis(update,context,tip):
    args=context.args
    if len(args)<3:
        await update.message.reply_text(f"Kullanim: /{tip.lower()} HISSE FIYAT LOT")
        return
    hisse=args[0].upper()
    try:
        kf=float(args[1].replace(",","."))
        kl=float(args[2].replace(",","."))
    except:
        await update.message.reply_text("Fiyat ve lot sayi olmali!")
        return
    ort,acik,acik_m=hesapla(hisse)
    if ort==0:
        await update.message.reply_text(f"{hisse} icin acik pozisyon yok!")
        return
    if kl>acik:
        await update.message.reply_text(f"Kapanacak lot ({fn(kl,0)}) acik lottan ({fn(acik,0)}) fazla!")
        return
    kz_tl=(kf-ort)*kl
    kz_pct=((kf/ort)-1)*100
    tarih=datetime.now().strftime("%d.%m.%Y %H:%M")
    ws=get_islemler()
    nid=yeni_id()
    ws.append_row([nid,hisse,tip.upper(),tarih,"","","",kf,kl,round(kz_tl,2),round(kz_pct,2),""])
    yort,yacik,yacik_m=hesapla(hisse)
    ap=ana_para()
    msg=(f"KAPANIS: *{hisse} - {tip.upper()}*\n"
f"Ortalama: `{fn(ort)}`\n"
f"Kapanis: `{fn(kf)}` | Lot: `{fn(kl,0)}`\n\n"
f"KAR/ZARAR:\n"
f"TL: `{fp(kz_tl)}`\n"
f"Yuzde: `{kz_pct:+.2f}%`\n\n")
    if yacik>0:
        hd=h(yort)
        msg+=(f"Kalan Lot: `{fn(yacik,0)}`\n"
f"STOP: `{fn(hd['stop'])}` | TP1: `{fn(hd['tp1'])}`\n\n")
    else:
        msg+="Pozisyon tamamen kapandi!\n\n"
    msg+=f"Ana Para: `{fp(ap)}`\nKaydedildi (#{nid})"
    await update.message.reply_text(msg,parse_mode="Markdown")

async def tp1_cmd(u,c): await kapanis(u,c,"TP1")
async def tp2_cmd(u,c): await kapanis(u,c,"TP2")
async def tp3_cmd(u,c): await kapanis(u,c,"TP3")
async def be_cmd(u,c): await kapanis(u,c,"BE")
async def stop_cmd(u,c): await kapanis(u,c,"STOP")

async def durum_cmd(update,context):
    if not context.args:
        await update.message.reply_text("Kullanim: /durum HISSE")
        return
    hisse=context.args[0].upper()
    ort,acik,acik_m=hesapla(hisse)
    if ort==0:
        await update.message.reply_text(f"{hisse} bulunamadi!")
        return
    hd=h(ort)
    durum="ACIK" if acik>0 else "KAPALI"
    msg=(f"*{hisse} - {durum}*\n"
f"Ortalama: `{fn(ort)}`\n"
f"Acik Lot: `{fn(acik,0)}`\n"
f"Acik Poz: `{fp(acik_m)}`\n\n"
f"HEDEFLER:\n"
f"STOP (%{hd['sp']}): `{fn(hd['stop'])}`\n"
f"BE: `{fn(hd['be'])}`\n"
f"TP1 (%{hd['t1']}): `{fn(hd['tp1'])}`\n"
f"TP2 (%{hd['t2']}): `{fn(hd['tp2'])}`\n"
f"TP3 (%{hd['t3']}): `{fn(hd['tp3'])}`")
    await update.message.reply_text(msg,parse_mode="Markdown")

async def ozet_cmd(update,context):
    try:
        rows=get_islemler().get_all_records()
    except:
        await update.message.reply_text("Henuz islem yok!")
        return
    if not rows:
        await update.message.reply_text("Henuz islem yok!")
        return
    hisseler=list(set(r.get("Hisse","") for r in rows if r.get("Hisse")))
    ap_bas=get_ayar("Ana Para")
    kz=sum(float(r.get("KZTL",0) or 0) for r in rows)
    msg=(f"*PORTFOY*\n"
f"Baslangic: `{fp(ap_bas)}`\n"
f"Guncel: `{fp(ap_bas+kz)}`\n"
f"Net K/Z: `{fp(kz)}`\n\n")
    for hs in sorted(hisseler):
        ort,acik,acik_m=hesapla(hs)
        hkz=sum(float(r.get("KZTL",0) or 0) for r in rows if str(r.get("Hisse","")).upper()==hs.upper())
        if acik>0:
            hd=h(ort)
            msg+=f"ACIK *{hs}* | Ort:`{fn(ort)}` | Lot:`{fn(acik,0)}`\nSTOP:`{fn(hd['stop'])}` TP1:`{fn(hd['tp1'])}`\n\n"
        else:
            msg+=f"KAPALI *{hs}* K/Z:`{fp(hkz)}`\n\n"
    await update.message.reply_text(msg,parse_mode="Markdown")

async def stats_cmd(update,context):
    try:
        rows=get_islemler().get_all_records()
    except:
        await update.message.reply_text("Henuz islem yok!")
        return
    krows=[r for r in rows if str(r.get("Tip","")).upper() in ["TP1","TP2","TP3","BE","STOP"]]
    if not krows:
        await update.message.reply_text("Henuz kapanmis islem yok!")
        return
    kazanli=[r for r in krows if float(r.get("KZTL",0) or 0)>0]
    zarar=[r for r in krows if float(r.get("KZTL",0) or 0)<=0]
    tkz=sum(float(r.get("KZTL",0) or 0) for r in krows)
    ap=get_ayar("Ana Para")
    ko=len(kazanli)/len(krows)*100 if krows else 0
    msg=(f"*ISTATISTIKLER*\n"
f"Net K/Z: `{fp(tkz)}` ({tkz/ap*100:+.2f}%)\n"
f"Toplam islem: {len(krows)}\n"
f"Karli: {len(kazanli)} | Zararli: {len(zarar)}\n"
f"Kazanma: `{ko:.1f}%`\n"
f"TP1:{sum(1 for r in krows if str(r.get('Tip','')).upper()=='TP1')} "
f"TP2:{sum(1 for r in krows if str(r.get('Tip','')).upper()=='TP2')} "
f"TP3:{sum(1 for r in krows if str(r.get('Tip','')).upper()=='TP3')} "
f"STOP:{sum(1 for r in krows if str(r.get('Tip','')).upper()=='STOP')}")
    await update.message.reply_text(msg,parse_mode="Markdown")

async def ayarlar_cmd(update,context):
    msg=(f"*AYARLAR*\n"
f"Ana Para: `{fp(get_ayar('Ana Para'))}`\n"
f"Stop: `{get_ayar('Stop')}%`\n"
f"TP1: `{get_ayar('TP1')}%`\n"
f"TP2: `{get_ayar('TP2')}%`\n"
f"TP3: `{get_ayar('TP3')}%`")
    await update.message.reply_text(msg,parse_mode="Markdown")

async def set_cmd(update,context):
    pm={"stop":"Stop","tp1":"TP1","tp2":"TP2","tp3":"TP3","para":"Ana Para"}
    if len(context.args)<2 or context.args[0].lower() not in pm:
        await update.message.reply_text("Kullanim: /set stop 10")
        return
    try:
        v=float(context.args[1].replace(",","."))
    except:
        await update.message.reply_text("Deger sayi olmali!")
        return
    p=pm[context.args[0].lower()]
    set_ayar(p,v)
    await update.message.reply_text(f"{p} -> {v} guncellendi!")

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
    logger.info("Bot baslatiliyor...")
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
