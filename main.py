import os, threading, csv, datetime, re, uuid, zipfile, time, asyncio
from flask import Flask, send_from_directory, send_file
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN")
print(f">>> TOKEN EXISTE? {bool(TOKEN)} - Tamanho: {len(TOKEN) if TOKEN else 0}")

ARQ_FUNC = "funcionarios.csv"
ARQ_CAD = "cadastros_fotos.csv"
ARQ_INV = "inventario_fotos.csv"
PASTA_FOTOS = "fotos"
os.makedirs(PASTA_FOTOS, exist_ok=True)

for arq, header in [(ARQ_CAD, ["chapa","nome","funcao","lider_imediato","coordenador","telefone","id_telegram"]),(ARQ_INV, ["data_registro","chapa","nome","funcao","lider_imediato","coordenador","telefone","tipo_item","patrimonio","foto1","foto2","foto3"])]:
    if not os.path.exists(arq):
        with open(arq, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

CHAPA, TELEFONE, MENU, PATRIMONIO, FOTO1, FOTO2, FOTO3 = range(7)

def formatar_telefone(t):
    if not t: return ""
    nums = re.sub(r'\D', '', str(t))
    if nums.startswith('55') and len(nums) > 11: nums = nums[2:]
    if len(nums) > 11: nums = nums[-11:]
    return f"{nums[:2]}-{nums[2:]}" if len(nums)>=10 else nums

def buscar_na_base_mestra(chapa):
    try:
        chapa_6 = str(chapa).strip().zfill(6)
        with open(ARQ_FUNC, encoding="utf-8-sig") as f:
            primeira = f.readline(); f.seek(0); delim = ";" if ";" in primeira else ","
            reader = csv.DictReader(f, delimiter=delim)
            reader.fieldnames = [c.strip().lower().replace(" ","_").replace("\ufeff","") for c in reader.fieldnames]
            ch_col = reader.fieldnames[0]
            nome_col = next((c for c in reader.fieldnames if "nome" in c), None)
            func_col = next((c for c in reader.fieldnames if "funcao" in c or "cargo" in c), None)
            lider_col = next((c for c in reader.fieldnames if "lider" in c), None)
            coord_col = next((c for c in reader.fieldnames if "coord" in c), None)
            for r in reader:
                if str(r.get(ch_col,"")).strip().zfill(6)==chapa_6:
                    return {"nome": str(r.get(nome_col,"")).upper(), "funcao": str(r.get(func_col,"")).upper(), "lider": str(r.get(lider_col,"")).upper(), "coord": str(r.get(coord_col,"")).upper()}
    except Exception as e:
        print(f"Erro base: {e}")
    return None

def buscar_cadastro(chapa):
    try:
        with open(ARQ_CAD, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["chapa"]==chapa: return r
    except: pass
    return None

def salvar_cadastro(d):
    rows=[]
    try:
        with open(ARQ_CAD, encoding="utf-8") as f: rows=list(csv.DictReader(f))
    except: pass
    rows=[r for r in rows if r["chapa"]!=d["chapa"]]; rows.append(d)
    with open(ARQ_CAD, "w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=["chapa","nome","funcao","lider_imediato","coordenador","telefone","id_telegram"]); w.writeheader(); w.writerows(rows)

def patrimonio_existe(p):
    try:
        with open(ARQ_INV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["patrimonio"].upper()==p.upper(): return True
    except: pass
    return False

app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "BOT FOTOS ON"
@app_flask.route('/fotos/<path:filename>')
def foto(filename): return send_from_directory(PASTA_FOTOS, filename)
@app_flask.route('/base')
def base():
    html="<h2>BASE FOTOS</h2><a href=/exportar>CSV</a> | <a href=/exportar_rar>ZIP</a><br><br><table border=1><tr><th>CHAPA</th><th>NOME</th><th>TEL</th><th>FOTOS</th><th>PAT</th><th>TIPO</th></tr>"
    try:
        with open(ARQ_INV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                imgs="".join([f"<a href=/{r.get(k,'')} target=_blank><img src=/{r.get(k,'')} width=80></a>" for k in ["foto1","foto2","foto3"] if r.get(k)])
                html+=f"<tr><td>{r.get('chapa')}</td><td>{r.get('nome')}</td><td>{r.get('telefone')}</td><td>{imgs}</td><td>{r.get('patrimonio')}</td><td>{r.get('tipo_item')}</td></tr>"
    except Exception as e: html+=f"Erro {e}"
    return html+"</table>"

@app_flask.route('/exportar')
def exp(): return send_file(ARQ_INV, as_attachment=True)
@app_flask.route('/exportar_rar')
def exprar():
    zp="fotos.zip"
    with zipfile.ZipFile(zp,'w') as z:
        if os.path.exists(ARQ_INV): z.write(ARQ_INV)
        try:
            with open(ARQ_INV, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    for k in ["foto1","foto2","foto3"]:
                        p=r.get(k,"")
                        if p and os.path.exists(p): z.write(p)
        except: pass
    return send_file(zp, as_attachment=True)

def run_flask():
    app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Sistema Fotos Patrimonio\nEnvie sua CHAPA:")
    return CHAPA

async def chapa_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa=update.message.text.strip().zfill(6)
    dados=buscar_na_base_mestra(chapa)
    if not dados:
        await update.message.reply_text(f"Chapa {chapa} nao existe")
        return CHAPA
    cad=buscar_cadastro(chapa)
    if cad and cad.get("telefone"):
        context.user_data.update(cad)
        kb=[[KeyboardButton("🔧 Maquina de Fusao"), KeyboardButton("📡 OTDR")]]
        await update.message.reply_text(f"Bem vindo {cad['nome']}! Escolha:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return MENU
    context.user_data["chapa"]=chapa
    context.user_data["dados_mestra"]=dados
    kb=[[KeyboardButton("📱 Compartilhar telefone", request_contact=True)]]
    await update.message.reply_text(f"CHAPA OK: {dados['nome']}\nCompartilhe telefone:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return TELEFONE

async def telefone_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tel_raw=update.message.contact.phone_number if update.message.contact else update.message.text
    tel=formatar_telefone(tel_raw)
    m=context.user_data["dados_mestra"]
    dados={"chapa": context.user_data["chapa"], "nome": m["nome"], "funcao": m["funcao"], "lider_imediato": m["lider"], "coordenador": m["coord"], "telefone": tel, "id_telegram": str(update.effective_user.id)}
    salvar_cadastro(dados)
    context.user_data.update(dados)
    kb=[[KeyboardButton("🔧 Maquina de Fusao"), KeyboardButton("📡 OTDR")]]
    await update.message.reply_text(f"Tel {tel} salvo! Escolha:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return MENU

async def menu_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t=update.message.text.upper()
    context.user_data["tipo_item"]="MAQUINA DE FUSAO" if "FUS" in t else "OTDR"
    await update.message.reply_text(f"Escolheu {context.user_data['tipo_item']}\nDigite o PATRIMONIO:")
    return PATRIMONIO

async def patrimonio_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pat=update.message.text.strip().upper()
    if patrimonio_existe(pat):
        await update.message.reply_text(f"Pat {pat} ja existe! Digite outro:")
        return PATRIMONIO
    context.user_data["patrimonio"]=pat
    await update.message.reply_text(f"Pat {pat} OK! Envie FOTO 1:")
    return FOTO1

async def baixar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ph=update.message.photo[-1]
    file=await context.bot.get_file(ph.file_id)
    nome=f"{context.user_data['patrimonio']}_{uuid.uuid4().hex[:6]}.jpg"
    caminho=os.path.join(PASTA_FOTOS, nome)
    await file.download_to_drive(caminho)
    return caminho

async def foto1_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Envie FOTO!")
        return FOTO1
    context.user_data["foto1"]=await baixar(update, context)
    await update.message.reply_text("Foto1 OK! Envie FOTO 2:")
    return FOTO2

async def foto2_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Envie FOTO!")
        return FOTO2
    context.user_data["foto2"]=await baixar(update, context)
    await update.message.reply_text("Foto2 OK! Envie FOTO 3:")
    return FOTO3

async def foto3_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Envie FOTO!")
        return FOTO3
    context.user_data["foto3"]=await baixar(update, context)
    with open(ARQ_INV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([datetime.datetime.now().strftime("%d/%m/%Y %H:%M"), context.user_data["chapa"], context.user_data["nome"], context.user_data["funcao"], context.user_data["lider_imediato"], context.user_data["coordenador"], context.user_data["telefone"], context.user_data["tipo_item"], context.user_data["patrimonio"], context.user_data["foto1"], context.user_data["foto2"], context.user_data["foto3"]])
    kb=[[KeyboardButton("🔧 Maquina de Fusao"), KeyboardButton("📡 OTDR")]]
    await update.message.reply_text(f"✅ SALVO {context.user_data['patrimonio']}!", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado. /start")
    return ConversationHandler.END

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    print(">>> INICIANDO BOT...")
    if not TOKEN:
        print(">>> SEM TOKEN")
        while True: time.sleep(10)
    print(f">>> TOKEN OK TAM {len(TOKEN)} - CRIANDO APP")
    
    # FIX PARA PYTHON 3.14
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except: pass

    application = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHAPA: [MessageHandler(filters.TEXT & ~filters.COMMAND, chapa_step)],
            TELEFONE: [MessageHandler(filters.ALL, telefone_step)],
            MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_step)],
            PATRIMONIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, patrimonio_step)],
            FOTO1: [MessageHandler(filters.PHOTO, foto1_step)],
            FOTO2: [MessageHandler(filters.PHOTO, foto2_step)],
            FOTO3: [MessageHandler(filters.PHOTO, foto3_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(conv)
    print(">>> BOT FOTOS ON - PRONTO PRA RECEBER /start")
    application.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
