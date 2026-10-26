import os, threading, csv, datetime, re, uuid, zipfile
from flask import Flask, send_from_directory, send_file, request
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes
from PIL import Image, ImageDraw, ImageFont

TOKEN = os.environ.get("BOT_TOKEN")
ARQ_FUNC = "funcionarios.csv"
ARQ_CAD = "cadastros_fotos.csv"
ARQ_INV = "inventario_fotos.csv"
PASTA_FOTOS = "fotos"
PASTA_MASCARAS = "mascaras"
os.makedirs(PASTA_FOTOS, exist_ok=True)
os.makedirs(PASTA_MASCARAS, exist_ok=True)

for arq, header in [(ARQ_CAD, ["chapa","nome","funcao","lider_imediato","coordenador","telefone","id_telegram"]),(ARQ_INV, ["data_registro","chapa","nome","funcao","lider_imediato","coordenador","telefone","tipo_item","patrimonio_maquina","patrimonio_otdr","foto_maquina1","foto_maquina2","foto_maquina3","foto_otdr1","foto_otdr2","foto_otdr3","mascara_arquivo"])]:
    if not os.path.exists(arq):
        with open(arq, "w", newline="", encoding="utf-8") as f: csv.writer(f).writerow(header)

CHAPA, TELEFONE, MAQ_PAT, MAQ_F1, MAQ_F2, MAQ_F3, OTDR_PAT, OTDR_F1, OTDR_F2, OTDR_F3, FINAL = range(11)

def formatar_telefone(t):
    if not t: return ""
    nums = re.sub(r'\D', '', str(t))
    if nums.startswith('55') and len(nums) > 11: nums = nums[2:]
    if len(nums) > 11: nums = nums[-11:]
    return f"{nums[:2]}-{nums[2:]}" if len(nums)>=10 else nums

def buscar_na_base_mestra(chapa):
    try:
        chapa_6 = str(chapa).strip().zfill(6)
        chapa_sem_zero = str(chapa).strip().lstrip("0")
        with open(ARQ_FUNC, encoding="utf-8-sig") as f:
            primeira = f.readline(); f.seek(0)
            delim = ";" if ";" in primeira else ","
            reader = csv.DictReader(f, delimiter=delim)
            reader.fieldnames = [c.strip().lower().replace(" ","_").replace("\ufeff","") for c in reader.fieldnames]
            ch_col = reader.fieldnames[0]
            nome_col = next((c for c in reader.fieldnames if "nome" in c), None)
            func_col = next((c for c in reader.fieldnames if "funcao" in c or "cargo" in c), None)
            lider_col = next((c for c in reader.fieldnames if "lider" in c), None)
            coord_col = next((c for c in reader.fieldnames if "coord" in c), None)
            for r in reader:
                c = str(r.get(ch_col,"")).strip()
                if c.zfill(6)==chapa_6 or c==chapa_sem_zero or c==str(chapa).strip():
                    return {"nome": str(r.get(nome_col,"")).upper(), "funcao": str(r.get(func_col,"")).upper(), "lider": str(r.get(lider_col,"")).upper(), "coord": str(r.get(coord_col,"")).upper()}
    except: pass
    return None
def buscar_cadastro(chapa):
    try:
        with open(ARQ_CAD, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["chapa"].zfill(6)==str(chapa).zfill(6): return r
    except: pass
    return None
def salvar_cadastro(d):
    rows=[]
    try:
        with open(ARQ_CAD, encoding="utf-8") as f: rows=list(csv.DictReader(f))
    except: pass
    rows=[r for r in rows if r["chapa"].zfill(6)!=d["chapa"].zfill(6)]; rows.append(d)
    with open(ARQ_CAD, "w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=["chapa","nome","funcao","lider_imediato","coordenador","telefone","id_telegram"]); w.writeheader(); w.writerows(rows)
def patrimonio_existe(p):
    try:
        with open(ARQ_INV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("patrimonio_maquina","").upper()==p.upper() or r.get("patrimonio_otdr","").upper()==p.upper(): return True
    except: pass
    return False
def chapa_ja_cadastrou(chapa):
    try:
        chapa_6 = str(chapa).strip().zfill(6)
        with open(ARQ_INV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get('chapa','')).zfill(6) == chapa_6:
                    return True, r
    except: pass
    return False, None

def gerar_mascara(dados):
    data_hora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    texto = f"MASCARA {dados['pat_maquina']} | {dados['pat_otdr']} | CHAPA {dados['chapa']} | {data_hora}"
    try:
        os.makedirs(PASTA_MASCARAS, exist_ok=True)
        nome_base = f"{dados['pat_maquina']}_{dados['pat_otdr']}_{uuid.uuid4().hex[:4]}"
        caminho_txt = os.path.join(PASTA_MASCARAS, f"{nome_base}.txt")
        caminho_png = os.path.join(PASTA_MASCARAS, f"{nome_base}.png")
        with open(caminho_txt, "w", encoding="utf-8") as f:
            f.write(f"MASCARA - PATRIMONIO\nMAQUINA FUSAO: {dados['pat_maquina']}\nOTDR: {dados['pat_otdr']}\nCHAPA: {dados['chapa']}\nCOLABORADOR: {dados['nome']}\nTEL: {dados['telefone']}\nFUNCAO: {dados['funcao']}\nSUPERVISOR/LIDER: {dados['lider_imediato']}\nCOORDENADOR: {dados.get('coordenador','')}\nDATA: {data_hora}")
        W, H = 900, 580
        BG = (238,238,238)
        img = Image.new('RGB', (W, H), BG)
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        def bold(x,y,t,c, sz=20):
            try: f = ImageFont.truetype("DejaVuSans-Bold.ttf", sz)
            except: f = font
            draw.text((x,y),t,fill=c,font=f)
        def normal(x,y,t,c, sz=16):
            try: f = ImageFont.truetype("DejaVuSans-Bold.ttf", sz)
            except: f = font
            draw.text((x,y),t,fill=c,font=f)
        def small(x,y,t,c, sz=11):
            try: f = ImageFont.truetype("DejaVuSans.ttf", sz)
            except: f = font
            draw.text((x,y),t,fill=c,font=f)
        AZUL_ESC = (15,58,110)
        draw.rounded_rectangle([(30,50),(870,555)], radius=28, fill=(255,255,255))
        draw.rounded_rectangle([(155,12),(745,78)], radius=30, fill=(15,76,143))
        bold(215,26,"MASCARA - PATRIMONIO",(255,255,255),22)
        bold(70,105,"MAQUINA FUSAO:",AZUL_ESC,17)
        normal(70,130,f"{dados['pat_maquina']}",(0,0,0),22)
        bold(500,105,"OTDR:",AZUL_ESC,17)
        normal(500,130,f"{dados['pat_otdr']}",(0,0,0),22)
        draw.line([(65,165),(835,165)], fill=(230,230,230), width=2)
        bold(70,185,"CHAPA:",AZUL_ESC,14)
        normal(70,205,f"{dados['chapa']}",(15,35,70),14)
        # NOME COMPLETO SEM CORTAR - FONTE AUTO
        nome_completo = dados['nome'].strip()
        sz_nome = 13 if len(nome_completo) > 28 else 14
        bold(200,185,"COLABORADOR:",AZUL_ESC,14)
        normal(200,205,f"{nome_completo}",(0,0,0),sz_nome)
        bold(620,185,"TEL:",AZUL_ESC,14)
        normal(620,205,f"{dados['telefone']}",(15,35,70),13)
        # FUNCAO COMPLETA
        bold(70,245,"FUNCAO:",AZUL_ESC,14)
        normal(150,245,f"{dados['funcao']}",(15,35,70),14)
        draw.rounded_rectangle([(50,285),(850,470)], radius=22, fill=(185,211,240))
        draw.rectangle([(50,380),(850,470)], fill=(185,211,240))
        # LIDER E COORD COMPLETOS
        lider_full = dados['lider_imediato'].strip()
        coord_full = dados.get('coordenador','').strip()
        sz_lider = 12 if len(lider_full) > 22 else 13
        sz_coord = 12 if len(coord_full) > 22 else 13
        bold(70,300,"SUPERVISOR/LIDER:",AZUL_ESC,13)
        normal(70,325,f"{lider_full}",(0,0,0),sz_lider)
        draw.line([(430,295),(430,395)], fill=(140,180,220), width=1)
        bold(450,300,"COORDENADOR:",AZUL_ESC,13)
        normal(450,325,f"{coord_full}",(0,0,0),sz_coord)
        # DATA PEQUENA ULTIMA LINHA
        small(65,485,f"DATA: {data_hora}",(90,90,90),11)
        small(650,485,f"ID: {nome_base[:20].upper()}",(90,90,90),10)
        img.save(caminho_png, quality=95, optimize=True)
        return caminho_txt, caminho_png, texto
    except Exception as e:
        print(f"ERRO MASCARA: {e}")
        return caminho_txt if 'caminho_txt' in locals() else "", caminho_png if 'caminho_png' in locals() else "", texto

def apagar_tudo_da_chapa(chapa):
    chapa = str(chapa).strip().zfill(6)
    try:
        novas=[]
        with open(ARQ_INV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get('chapa','')).zfill(6)!=chapa: novas.append(r)
                else:
                    for k in ["foto_maquina1","foto_maquina2","foto_maquina3","foto_otdr1","foto_otdr2","foto_otdr3","mascara_arquivo"]:
                        caminho = r.get(k,'')
                        if caminho and os.path.exists(caminho):
                            try: os.remove(caminho)
                            except: pass
        with open(ARQ_INV, "w", newline="", encoding="utf-8") as f:
            w=csv.DictWriter(f, fieldnames=["data_registro","chapa","nome","funcao","lider_imediato","coordenador","telefone","tipo_item","patrimonio_maquina","patrimonio_otdr","foto_maquina1","foto_maquina2","foto_maquina3","foto_otdr1","foto_otdr2","foto_otdr3","mascara_arquivo"])
            w.writeheader(); w.writerows(novas)
    except: pass

app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "BOT ON - NOME COMPLETO"
@app_flask.route('/fotos/<path:filename>')
def foto(filename): return send_from_directory(PASTA_FOTOS, filename)
@app_flask.route('/mascaras/<path:filename>')
def masc(filename): return send_from_directory(PASTA_MASCARAS, filename)
@app_flask.route('/apagar/<chapa>')
def apagar_chapa_url(chapa): apagar_tudo_da_chapa(chapa); return f"<script>alert('Chapa {chapa} apagada!'); window.location='/base';</script>"
@app_flask.route('/exportar')
def exp(): return send_file(ARQ_INV, as_attachment=True)
@app_flask.route('/exportar_zip')
def exportar_zip():
    zip_name = f"export_fotos_{datetime.datetime.now().strftime('%d%m%Y_%H%M')}.zip"
    zip_path = os.path.join("/tmp", zip_name)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(ARQ_INV): z.write(ARQ_INV, arcname="inventario_fotos.csv")
        if os.path.exists(ARQ_CAD): z.write(ARQ_CAD, arcname="cadastros_fotos.csv")
        for pasta in [PASTA_FOTOS, PASTA_MASCARAS]:
            if os.path.exists(pasta):
                for arquivo in os.listdir(pasta):
                    caminho = os.path.join(pasta, arquivo)
                    if os.path.isfile(caminho): z.write(caminho, arcname=os.path.join(pasta, arquivo))
    return send_file(zip_path, as_attachment=True, download_name=zip_name)
@app_flask.route('/apagar_chapa', methods=['GET','POST'])
def apagar_chapa_page():
    if request.method == 'POST':
        chapa = request.form.get('chapa','').strip()
        if chapa: apagar_tudo_da_chapa(chapa)
        return f"<h2>Chapa {chapa} apagada!</h2><a href=/base>Voltar</a>"
    return """<form method='POST'>CHAPA: <input name='chapa' required><button>APAGAR</button></form>"""
@app_flask.route('/base')
def base():
    chapa_filtro = request.args.get('chapa','').strip()
    html = f"""
    <html><head><meta charset='utf-8'><title>BASE NOME COMPLETO</title>
    <style>
    body{{font-family:Arial;padding:20px;background:#f5f6f8}}
    table{{width:100%;border-collapse:collapse;background:white}}
    th,td{{padding:8px;border:1px solid #ddd;text-align:center;font-size:11px;vertical-align:middle}}
    th{{background:#0F4C8F;color:white}}
    .foto-padrao{{width:50px;height:50px;object-fit:cover;border-radius:4px;border:1px solid #ccc;margin:2px}}
    .foto-padrao:hover{{transform:scale(4);z-index:100;position:relative}}
    .mascara-preview{{width:50px;height:50px;object-fit:cover;border-radius:4px;border:1px solid #0F4C8F;margin:2px;background:white}}
    .mascara-preview:hover{{transform:scale(6);z-index:100;position:relative}}
    .btn-apagar{{background:#dc3545;color:white;padding:5px 8px;border-radius:4px;text-decoration:none;font-size:11px}}
    </style></head><body>
    <h2>BASE - NOME COMPLETO</h2>
    <form method='GET'>CHAPA: <input name='chapa' value='{chapa_filtro}'><button>BUSCAR</button> <a href='/base'><button type='button'>LIMPAR</button></a> <a href='/apagar_chapa'><button type='button' style='background:orange;color:white'>APAGAR CHAPA</button></a></form><br>
    <table><tr><th>DATA</th><th>CHAPA</th><th>NOME COMPLETO</th><th>MAQ</th><th>OTDR</th><th>FOTOS MAQ</th><th>FOTOS OTDR</th><th>MASCARA</th><th>ACAO</th></tr>
    """
    try:
        with open(ARQ_INV, encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            if chapa_filtro: reader = [r for r in reader if chapa_filtro.zfill(6) in str(r.get('chapa','')).zfill(6)]
            for r in reader:
                f_maq = "".join([f"<a href=/{r.get(k,'')} target=_blank><img class='foto-padrao' src=/{r.get(k,'')}></a>" for k in ["foto_maquina1","foto_maquina2","foto_maquina3"] if r.get(k) and os.path.exists(r.get(k,''))])
                f_otdr = "".join([f"<a href=/{r.get(k,'')} target=_blank><img class='foto-padrao' src=/{r.get(k,'')}></a>" for k in ["foto_otdr1","foto_otdr2","foto_otdr3"] if r.get(k) and os.path.exists(r.get(k,''))])
                masc = f"<a href=/{r.get('mascara_arquivo','')} target=_blank><img class='mascara-preview' src=/{r.get('mascara_arquivo','')}></a>" if r.get('mascara_arquivo') and os.path.exists(r.get('mascara_arquivo','')) else "-"
                html+=f"<tr><td>{r.get('data_registro','')}</td><td><b>{r.get('chapa','')}</b></td><td style='text-align:left;font-weight:bold'>{r.get('nome','')}</td><td>{r.get('patrimonio_maquina','')}</td><td>{r.get('patrimonio_otdr','')}</td><td>{f_maq or '-'}</td><td>{f_otdr or '-'}</td><td>{masc}</td><td><a class='btn-apagar' href='/apagar/{r.get('chapa','')}'>APAGAR</a></td></tr>"
    except Exception as e: html+=f"<tr><td colspan=9>Erro: {e}</td></tr>"
    html+="</table><br><a href='/exportar_zip' style='background:green;color:white;padding:10px;text-decoration:none;border-radius:5px'>📦 Exportar ZIP</a></body></html>"
    return html

def run_flask(): app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("📸 Sistema Fotos Patrimonio\nEnvie sua CHAPA:")
    return CHAPA
async def chapa_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa=update.message.text.strip().zfill(6)
    dados=buscar_na_base_mestra(chapa)
    if not dados: await update.message.reply_text(f"❌ Chapa {chapa} nao existe"); return CHAPA
    ja_cad, reg = chapa_ja_cadastrou(chapa)
    if ja_cad:
        await update.message.reply_text(f"⛔ CHAPA {chapa} JA CADASTRADA!\nMAQ: {reg.get('patrimonio_maquina','')} OTDR: {reg.get('patrimonio_otdr','')}\nPara novo: /base > APAGAR > /start")
        return ConversationHandler.END
    cad=buscar_cadastro(chapa)
    if cad and cad.get("telefone"):
        context.user_data.update(cad)
        await update.message.reply_text(f"Bem vindo {cad['nome']}!\nDigite PATRIMONIO da MAQUINA:")
        return MAQ_PAT
    context.user_data["chapa"]=chapa; context.user_data["dados_mestra"]=dados
    kb=[[KeyboardButton("📱 Compartilhar telefone", request_contact=True)]]
    await update.message.reply_text(f"CHAPA OK: {dados['nome']}\nCompartilhe telefone:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return TELEFONE
async def telefone_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tel_raw=update.message.contact.phone_number if update.message.contact else update.message.text
    tel=formatar_telefone(tel_raw)
    m=context.user_data["dados_mestra"]
    d={"chapa": context.user_data["chapa"], "nome": m["nome"], "funcao": m["funcao"], "lider_imediato": m["lider"], "coordenador": m["coord"], "telefone": tel, "id_telegram": str(update.effective_user.id)}
    salvar_cadastro(d); context.user_data.update(d)
    await update.message.reply_text(f"Tel {tel} salvo!\nDigite PATRIMONIO da MAQUINA:")
    return MAQ_PAT
async def baixar(update, context, prefixo):
    ph=update.message.photo[-1]; file=await context.bot.get_file(ph.file_id)
    nome=f"{prefixo}_{uuid.uuid4().hex[:6]}.jpg"; caminho=os.path.join(PASTA_FOTOS, nome)
    await file.download_to_drive(caminho); return caminho
async def maq_pat_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pat=update.message.text.strip().upper()
    if patrimonio_existe(pat): await update.message.reply_text(f"Pat {pat} ja existe! Outro:"); return MAQ_PAT
    context.user_data["pat_maquina"]=pat; await update.message.reply_text(f"MAQUINA {pat}\nFOTO 1:"); return MAQ_F1
async def maq_f1_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return MAQ_F1
    context.user_data["maq_f1"]=await baixar(update, context, context.user_data["pat_maquina"]+"_MAQ1")
    await update.message.reply_text("Foto1 OK! Foto2:"); return MAQ_F2
async def maq_f2_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return MAQ_F2
    context.user_data["maq_f2"]=await baixar(update, context, context.user_data["pat_maquina"]+"_MAQ2")
    await update.message.reply_text("Foto2 OK! Foto3:"); return MAQ_F3
async def maq_f3_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return MAQ_F3
    context.user_data["maq_f3"]=await baixar(update, context, context.user_data["pat_maquina"]+"_MAQ3")
    await update.message.reply_text("MAQ OK! PATRIMONIO OTDR:"); return OTDR_PAT
async def otdr_pat_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pat=update.message.text.strip().upper()
    if pat==context.user_data.get("pat_maquina"): await update.message.reply_text("OTDR != MAQUINA! Outro:"); return OTDR_PAT
    if patrimonio_existe(pat): await update.message.reply_text(f"Pat {pat} ja existe! Outro:"); return OTDR_PAT
    context.user_data["pat_otdr"]=pat; await update.message.reply_text(f"OTDR {pat}\nFOTO1 OTDR:"); return OTDR_F1
async def otdr_f1_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return OTDR_F1
    context.user_data["otdr_f1"]=await baixar(update, context, context.user_data["pat_otdr"]+"_OTDR1")
    await update.message.reply_text("Foto1 OTDR OK! Foto2:"); return OTDR_F2
async def otdr_f2_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return OTDR_F2
    context.user_data["otdr_f2"]=await baixar(update, context, context.user_data["pat_otdr"]+"_OTDR2")
    await update.message.reply_text("Foto2 OK! Foto3:"); return OTDR_F3
async def otdr_f3_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return OTDR_F3
    context.user_data["otdr_f3"]=await baixar(update, context, context.user_data["pat_otdr"]+"_OTDR3")
    kb=[[KeyboardButton("✅ FINALIZAR E GERAR MASCARA")]]
    await update.message.reply_text(f"RESUMO MAQ:{context.user_data['pat_maquina']} OTDR:{context.user_data['pat_otdr']}\nFinalizar?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)); return FINAL
async def final_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "CANCELAR" in update.message.text.upper(): await update.message.reply_text("Cancelado /start"); return ConversationHandler.END
    try:
        await update.message.reply_text("⏳ Gerando mascara...")
        masc_txt, masc_png, texto_masc = gerar_mascara(context.user_data)
        data_reg = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        with open(ARQ_INV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([data_reg, context.user_data["chapa"], context.user_data["nome"], context.user_data["funcao"], context.user_data["lider_imediato"], context.user_data["coordenador"], context.user_data["telefone"], "KIT", context.user_data["pat_maquina"], context.user_data["pat_otdr"], context.user_data["maq_f1"], context.user_data["maq_f2"], context.user_data["maq_f3"], context.user_data["otdr_f1"], context.user_data["otdr_f2"], context.user_data["otdr_f3"], masc_png])
        await update.message.reply_text(f"✅ SALVO! {texto_masc}")
        if os.path.exists(masc_png):
            with open(masc_png, "rb") as photo: await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo, caption=f"MASCARA - {context.user_data['pat_maquina']} + {context.user_data['pat_otdr']}")
        await update.message.reply_text("Novo /start")
    except Exception as e: await update.message.reply_text(f"Erro: {e}")
    return ConversationHandler.END
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("Cancelado /start"); return ConversationHandler.END

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    import asyncio
    try: asyncio.set_event_loop(asyncio.new_event_loop())
    except: pass
    application = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(entry_points=[CommandHandler("start", start)], states={CHAPA: [MessageHandler(filters.TEXT & ~filters.COMMAND, chapa_step)], TELEFONE: [MessageHandler(filters.ALL, telefone_step)], MAQ_PAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, maq_pat_step)], MAQ_F1: [MessageHandler(filters.PHOTO, maq_f1_step)], MAQ_F2: [MessageHandler(filters.PHOTO, maq_f2_step)], MAQ_F3: [MessageHandler(filters.PHOTO, maq_f3_step)], OTDR_PAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, otdr_pat_step)], OTDR_F1: [MessageHandler(filters.PHOTO, otdr_f1_step)], OTDR_F2: [MessageHandler(filters.PHOTO, otdr_f2_step)], OTDR_F3: [MessageHandler(filters.PHOTO, otdr_f3_step)], FINAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, final_step)]}, fallbacks=[CommandHandler("cancel", cancel)])
    application.add_handler(conv)
    application.run_polling(drop_pending_updates=True)

if __name__=="__main__": main()
