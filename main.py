import os, threading, csv, datetime, re, uuid, zipfile, time, asyncio
from flask import Flask, send_from_directory, send_file, request
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes
from PIL import Image, ImageDraw, ImageFont

TOKEN = os.environ.get("BOT_TOKEN")
print(f">>> TOKEN EXISTE? {bool(TOKEN)}")

ARQ_FUNC = "funcionarios.csv"
ARQ_CAD = "cadastros_fotos.csv"
ARQ_INV = "inventario_fotos.csv"
PASTA_FOTOS = "fotos"
PASTA_MASCARAS = "mascaras"
os.makedirs(PASTA_FOTOS, exist_ok=True)
os.makedirs(PASTA_MASCARAS, exist_ok=True)

for arq, header in [(ARQ_CAD, ["chapa","nome","funcao","lider_imediato","coordenador","telefone","id_telegram"]),(ARQ_INV, ["data_registro","chapa","nome","funcao","lider_imediato","coordenador","telefone","tipo_item","patrimonio_maquina","patrimonio_otdr","foto_maquina1","foto_maquina2","foto_maquina3","foto_otdr1","foto_otdr2","foto_otdr3","mascara_arquivo"])]:
    if not os.path.exists(arq):
        with open(arq, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

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
    except Exception as e: print(f"Erro base: {e}")
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
                if r.get("patrimonio_maquina","").upper()==p.upper() or r.get("patrimonio_otdr","").upper()==p.upper(): return True
    except: pass
    return False

def gerar_mascara(dados):
    data_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    texto = f"""MASCARA DE IDENTIFICACAO

MAQUINA FUSAO: {dados['pat_maquina']}
OTDR: {dados['pat_otdr']}

DATA: {data_str}
CHAPA: {dados['chapa']} - {dados['nome']}
TEL: {dados['telefone']}

"""
    nome_txt = f"{dados['pat_maquina']}_{dados['pat_otdr']}_{uuid.uuid4().hex[:4]}.txt"
    caminho_txt = os.path.join(PASTA_MASCARAS, nome_txt)
    with open(caminho_txt, "w", encoding="utf-8") as f:
        f.write(texto)
    nome_png = nome_txt.replace(".txt",".png")
    caminho_png = os.path.join(PASTA_MASCARAS, nome_png)
    img = Image.new('RGB', (800, 400), color='white')
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
        font2 = ImageFont.truetype("arial.ttf", 22)
    except:
        font = ImageFont.load_default()
        font2 = ImageFont.load_default()
    draw.rectangle([(0,0),(800,400)], outline="black", width=4)
    draw.text((20,20), "MASCARA - PATRIMONIO", fill="black", font=font)
    draw.text((20,80), f"MAQUINA: {dados['pat_maquina']}", fill="black", font=font)
    draw.text((20,130), f"OTDR: {dados['pat_otdr']}", fill="black", font=font)
    draw.text((20,200), f"DATA: {data_str}", fill="black", font=font2)
    draw.text((20,240), f"CHAPA: {dados['chapa']} - {dados['nome']}", fill="black", font=font2)
    draw.text((20,280), f"TEL: {dados['telefone']}", fill="black", font=font2)
    draw.text((20,330), f"{dados['funcao']} | {dados['lider_imediato']}", fill="black", font=font2)
    img.save(caminho_png)
    return caminho_txt, caminho_png, texto

app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "BOT FOTOS ON - MASCARA"
@app_flask.route('/fotos/<path:filename>')
def foto(filename): return send_from_directory(PASTA_FOTOS, filename)
@app_flask.route('/mascaras/<path:filename>')
def masc(filename): return send_from_directory(PASTA_MASCARAS, filename)

@app_flask.route('/base')
def base():
    chapa_filtro = request.args.get('chapa','').strip()
    nome_filtro = request.args.get('nome','').strip().upper()
    pat_filtro = request.args.get('patrimonio','').strip().upper()
    filtro_ativo = chapa_filtro or nome_filtro or pat_filtro
    html = f"""
    <html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>BASE FOTOS</title>
    <style>
    body{{font-family:Arial;padding:20px;background:#f5f5f5}} .filtro{{background:white;padding:20px;border-radius:10px;box-shadow:0 2px 5px #0001;margin-bottom:20px}}
    input{{padding:10px;margin:5px;border:1px solid #ccc;border-radius:5px;width:180px}} button{{padding:10px 20px;background:#007bff;color:white;border:none;border-radius:5px;cursor:pointer;margin:2px}}
    button:hover{{background:#0056b3}} table{{background:white;width:100%;border-collapse:collapse;font-size:13px}} th,td{{padding:8px;text-align:left;border:1px solid #ddd}} th{{background:#007bff;color:white}} img{{border-radius:5px;margin:2px}} .total{{margin:15px 0;font-weight:bold;background:white;padding:10px;border-radius:5px}}
    </style></head><body>
    <h2>📸 BASE FOTOS - FILTRO POR CHAPA</h2>
    <div class='filtro'>
        <form method='GET' action='/base'>
            <b>FILTRAR:</b><br>
            CHAPA: <input type='text' name='chapa' placeholder='Ex: 001234' value='{chapa_filtro}'>
            NOME: <input type='text' name='nome' placeholder='Ex: JOAO' value='{nome_filtro}'>
            PATRIMONIO: <input type='text' name='patrimonio' placeholder='MAQ ou OTDR' value='{pat_filtro}'>
            <button type='submit'>🔍 BUSCAR</button>
            <a href='/base'><button type='button'>❌ LIMPAR</button></a>
        </form>
        <div style='margin-top:10px'><a href='/exportar'>📥 CSV</a> | <a href='/exportar_rar'>📦 ZIP</a></div>
    </div>
    """
    if filtro_ativo:
        html += f"<div class='total'>🔎 Filtro: CHAPA={chapa_filtro} NOME={nome_filtro} PAT={pat_filtro} | <a href='/base'>Ver todos</a></div>"
    html+="<table><tr><th>DATA</th><th>CHAPA</th><th>NOME</th><th>TEL</th><th>MAQ</th><th>OTDR</th><th>FOTOS MAQ</th><th>FOTOS OTDR</th><th>MASCARA</th></tr>"
    count=0; count_filtrado=0
    try:
        with open(ARQ_INV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                count+=1
                if chapa_filtro:
                    if r.get('chapa','').zfill(6) != chapa_filtro.zfill(6): continue
                if nome_filtro:
                    if nome_filtro not in r.get('nome','').upper(): continue
                if pat_filtro:
                    if pat_filtro not in r.get('patrimonio_maquina','').upper() and pat_filtro not in r.get('patrimonio_otdr','').upper(): continue
                count_filtrado+=1
                f_maq = "".join([f"<a href=/{r.get(k,'')} target=_blank><img src=/{r.get(k,'')} width=60 height=60 style='object-fit:cover'></a>" for k in ["foto_maquina1","foto_maquina2","foto_maquina3"] if r.get(k)])
                f_otdr = "".join([f"<a href=/{r.get(k,'')} target=_blank><img src=/{r.get(k,'')} width=60 height=60 style='object-fit:cover'></a>" for k in ["foto_otdr1","foto_otdr2","foto_otdr3"] if r.get(k)])
                masc_link = r.get('mascara_arquivo','')
                masc = f"<a href=/{masc_link} target=_blank><img src=/{masc_link} width=120><br>VER</a>" if masc_link else ""
                html+=f"<tr><td>{r.get('data_registro')}</td><td><b>{r.get('chapa')}</b></td><td>{r.get('nome')}<br><small>{r.get('funcao')}</small></td><td>{r.get('telefone')}</td><td><b>{r.get('patrimonio_maquina')}</b></td><td><b>{r.get('patrimonio_otdr')}</b></td><td>{f_maq}</td><td>{f_otdr}</td><td>{masc}</td></tr>"
    except Exception as e: html+=f"<tr><td colspan=9>Erro: {e}</td></tr>"
    if filtro_ativo:
        html+=f"</table><div class='total'>Encontrados: {count_filtrado} de {count} registros</div></body></html>"
    else:
        html+=f"</table><div class='total'>Total: {count} kits cadastrados</div></body></html>"
    return html

@app_flask.route('/exportar')
def exp(): return send_file(ARQ_INV, as_attachment=True)
@app_flask.route('/exportar_rar')
def exprar():
    zp="fotos_completo.zip"
    with zipfile.ZipFile(zp,'w') as z:
        if os.path.exists(ARQ_INV): z.write(ARQ_INV)
        for pasta in [PASTA_FOTOS, PASTA_MASCARAS]:
            for root,_,files in os.walk(pasta):
                for file in files:
                    z.write(os.path.join(root,file))
    return send_file(zp, as_attachment=True)

def run_flask():
    app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("📸 Sistema Fotos Patrimonio\n\nVamos fazer passo a passo:\n1- Maquina\n2- OTDR\n3- Gerar Mascara\n\nEnvie sua CHAPA:")
    return CHAPA

async def chapa_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa=update.message.text.strip().zfill(6)
    dados=buscar_na_base_mestra(chapa)
    if not dados:
        await update.message.reply_text(f"Chapa {chapa} nao existe na base")
        return CHAPA
    cad=buscar_cadastro(chapa)
    if cad and cad.get("telefone"):
        context.user_data.update(cad)
        await update.message.reply_text(f"Bem vindo {cad['nome']}!\n\nPASSO 1/7: Digite PATRIMONIO da MAQUINA DE FUSAO:")
        return MAQ_PAT
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
    await update.message.reply_text(f"Tel {tel} salvo!\n\nPASSO 1/7: Digite PATRIMONIO da MAQUINA DE FUSAO:")
    return MAQ_PAT

async def baixar(update, context, prefixo):
    ph=update.message.photo[-1]
    file=await context.bot.get_file(ph.file_id)
    nome=f"{prefixo}_{uuid.uuid4().hex[:6]}.jpg"
    caminho=os.path.join(PASTA_FOTOS, nome)
    await file.download_to_drive(caminho)
    return caminho

async def maq_pat_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pat=update.message.text.strip().upper()
    if patrimonio_existe(pat):
        await update.message.reply_text(f"Pat {pat} ja existe! Digite outro da MAQUINA:")
        return MAQ_PAT
    context.user_data["pat_maquina"]=pat
    await update.message.reply_text(f"✅ MAQUINA {pat}\n\nPASSO 2/7: Envie FOTO 1 da MAQUINA:")
    return MAQ_F1

async def maq_f1_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return MAQ_F1
    context.user_data["maq_f1"]=await baixar(update, context, context.user_data["pat_maquina"]+"_MAQ1")
    await update.message.reply_text("Foto 1 OK!\nPASSO 3/7: Envie FOTO 2 da MAQUINA:")
    return MAQ_F2

async def maq_f2_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return MAQ_F2
    context.user_data["maq_f2"]=await baixar(update, context, context.user_data["pat_maquina"]+"_MAQ2")
    await update.message.reply_text("Foto 2 OK!\nPASSO 4/7: Envie FOTO 3 da MAQUINA:")
    return MAQ_F3

async def maq_f3_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return MAQ_F3
    context.user_data["maq_f3"]=await baixar(update, context, context.user_data["pat_maquina"]+"_MAQ3")
    await update.message.reply_text("✅ MAQUINA COMPLETA!\n\nPASSO 5/7: Agora digite PATRIMONIO do OTDR:")
    return OTDR_PAT

async def otdr_pat_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pat=update.message.text.strip().upper()
    if pat==context.user_data.get("pat_maquina"):
        await update.message.reply_text("OTDR nao pode ser igual MAQUINA! Digite outro:")
        return OTDR_PAT
    if patrimonio_existe(pat):
        await update.message.reply_text(f"Pat {pat} ja existe! Digite outro do OTDR:")
        return OTDR_PAT
    context.user_data["pat_otdr"]=pat
    await update.message.reply_text(f"✅ OTDR {pat}\n\nPASSO 6/7: Envie FOTO 1 do OTDR:")
    return OTDR_F1

async def otdr_f1_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return OTDR_F1
    context.user_data["otdr_f1"]=await baixar(update, context, context.user_data["pat_otdr"]+"_OTDR1")
    await update.message.reply_text("Foto 1 OTDR OK!\nPASSO 7/7: Envie FOTO 2 do OTDR:")
    return OTDR_F2

async def otdr_f2_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return OTDR_F2
    context.user_data["otdr_f2"]=await baixar(update, context, context.user_data["pat_otdr"]+"_OTDR2")
    await update.message.reply_text("Foto 2 OTDR OK!\nPASSO 8/7: Envie FOTO 3 do OTDR:")
    return OTDR_F3

async def otdr_f3_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return OTDR_F3
    context.user_data["otdr_f3"]=await baixar(update, context, context.user_data["pat_otdr"]+"_OTDR3")
    resumo = f"""📋 RESUMO PARA GERAR MASCARA:

🔧 MAQUINA: {context.user_data['pat_maquina']}
📡 OTDR: {context.user_data['pat_otdr']}
👤 {context.user_data['chapa']} - {context.user_data['nome']}
📅 {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}

Fotos: 3 da Maquina + 3 do OTDR OK!

Deseja FINALIZAR?"""
    kb=[[KeyboardButton("✅ FINALIZAR E GERAR MASCARA")],[KeyboardButton("❌ CANCELAR")]]
    await update.message.reply_text(resumo, reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return FINAL

async def final_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "CANCELAR" in update.message.text.upper():
        await update.message.reply_text("Cancelado. /start para recomecar")
        return ConversationHandler.END
    masc_txt, masc_png, texto_masc = gerar_mascara(context.user_data)
    data_reg = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    with open(ARQ_INV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([data_reg, context.user_data["chapa"], context.user_data["nome"], context.user_data["funcao"], context.user_data["lider_imediato"], context.user_data["coordenador"], context.user_data["telefone"], "KIT MAQ+OTDR", context.user_data["pat_maquina"], context.user_data["pat_otdr"], context.user_data["maq_f1"], context.user_data["maq_f2"], context.user_data["maq_f3"], context.user_data["otdr_f1"], context.user_data["otdr_f2"], context.user_data["otdr_f3"], masc_png])
    await update.message.reply_text(f"✅ KIT SALVO COM SUCESSO!\n\n{texto_masc}\n\nMascara gerada!")
    await context.bot.send_document(chat_id=update.effective_chat.id, document=open(masc_txt, "rb"), filename=os.path.basename(masc_txt))
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=open(masc_png, "rb"), caption=f"MASCARA {context.user_data['pat_maquina']} + {context.user_data['pat_otdr']}")
    await update.message.reply_text("Para cadastrar outro KIT, digite /start", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True))
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado. /start")
    return ConversationHandler.END

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    try: asyncio.set_event_loop(asyncio.new_event_loop())
    except: pass
    print(f">>> TOKEN EXISTE? {bool(TOKEN)}")
    application = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHAPA: [MessageHandler(filters.TEXT & ~filters.COMMAND, chapa_step)],
            TELEFONE: [MessageHandler(filters.ALL, telefone_step)],
            MAQ_PAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, maq_pat_step)],
            MAQ_F1: [MessageHandler(filters.PHOTO, maq_f1_step)],
            MAQ_F2: [MessageHandler(filters.PHOTO, maq_f2_step)],
            MAQ_F3: [MessageHandler(filters.PHOTO, maq_f3_step)],
            OTDR_PAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, otdr_pat_step)],
            OTDR_F1: [MessageHandler(filters.PHOTO, otdr_f1_step)],
            OTDR_F2: [MessageHandler(filters.PHOTO, otdr_f2_step)],
            OTDR_F3: [MessageHandler(filters.PHOTO, otdr_f3_step)],
            FINAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, final_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(conv)
    print(">>> BOT FOTOS ON - MODO MASCARA + FILTRO CHAPA PRONTO")
    application.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
