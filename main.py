import os, threading, csv, datetime, re, uuid, zipfile, asyncio
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

# ===== MASCARA PRIMEIRA - ORIGINAL SIMPLES =====
def gerar_mascara(dados):
    data_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    texto = f"""MASCARA - PATRIMONIO
MAQUINA FUSAO: {dados['pat_maquina']}
OTDR: {dados['pat_otdr']}
DATA: {data_str}
CHAPA: {dados['chapa']} | COLABORADOR: {dados['nome']} | TEL: {dados['telefone']}
FUNCAO: {dados['funcao']}
SUPERVISOR/LIDER: {dados['lider_imediato']} | COORD: {dados.get('coordenador','')}
"""
    nome_txt = f"{dados['pat_maquina']}_{dados['pat_otdr']}_{uuid.uuid4().hex[:4]}.txt"
    caminho_txt = os.path.join(PASTA_MASCARAS, nome_txt)
    with open(caminho_txt, "w", encoding="utf-8") as f: f.write(texto)

    W, H = 1050, 350
    img = Image.new('RGB', (W, H), color='white')
    draw = ImageDraw.Draw(img)
    try:
        f_b = ImageFont.truetype("arialbd.ttf", 22)
        f_n = ImageFont.truetype("arial.ttf", 20)
    except:
        f_b = f_n = ImageFont.load_default()
    
    draw.rectangle([(0,0,W,50)], fill=(15,48,87))
    draw.text((20,12), f"MASCARA - PATRIMONIO | {data_str}", fill="white", font=f_b)
    
    draw.text((20,70), f"MAQUINA: {dados['pat_maquina']}  |  OTDR: {dados['pat_otdr']}", fill=(0,0,0), font=f_b)
    draw.text((20,110), f"CHAPA: {dados['chapa']} | COLABORADOR: {dados['nome']} | TEL: {dados['telefone']}", fill=(0,0,0), font=f_n)
    draw.text((20,145), f"FUNCAO: {dados['funcao']}", fill=(0,0,0), font=f_n)
    draw.text((20,185), f"SUPERVISOR/LIDER: {dados['lider_imediato']} | COORDENADOR: {dados.get('coordenador','')}", fill=(0,0,0), font=f_n)
    
    draw.line([(0,250,W,250)], fill=(200,200,200), width=2)

    nome_png = nome_txt.replace(".txt",".png")
    caminho_png = os.path.join(PASTA_MASCARAS, nome_png)
    img.save(caminho_png, quality=95)
    return caminho_txt, caminho_png, texto

def apagar_tudo_da_chapa(chapa):
    chapa = str(chapa).strip().zfill(6)
    res = {'inventario':0,'fotos':0,'cadastro':0}
    try:
        novas_linhas=[]
        with open(ARQ_INV, encoding="utf-8") as f:
            reader=list(csv.DictReader(f))
            for r in reader:
                if str(r.get('chapa','')).zfill(6)==chapa:
                    res['inventario']+=1
                    for k in ["foto_maquina1","foto_maquina2","foto_maquina3","foto_otdr1","foto_otdr2","foto_otdr3","mascara_arquivo"]:
                        caminho = r.get(k,'')
                        if caminho and os.path.exists(caminho):
                            try: os.remove(caminho); res['fotos']+=1
                            except: pass
                else: novas_linhas.append(r)
        with open(ARQ_INV, "w", newline="", encoding="utf-8") as f:
            w=csv.DictWriter(f, fieldnames=["data_registro","chapa","nome","funcao","lider_imediato","coordenador","telefone","tipo_item","patrimonio_maquina","patrimonio_otdr","foto_maquina1","foto_maquina2","foto_maquina3","foto_otdr1","foto_otdr2","foto_otdr3","mascara_arquivo"])
            w.writeheader(); w.writerows(novas_linhas)
    except Exception as e: print(f"Erro: {e}")
    try:
        novas=[]
        with open(ARQ_CAD, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get('chapa','')).zfill(6)!=chapa: novas.append(r)
                else: res['cadastro']=1
        with open(ARQ_CAD, "w", newline="", encoding="utf-8") as f:
            w=csv.DictWriter(f, fieldnames=["chapa","nome","funcao","lider_imediato","coordenador","telefone","id_telegram"])
            w.writeheader(); w.writerows(novas)
    except Exception as e: print(f"Erro: {e}")
    return res

app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "BOT FOTOS ON - PRIMEIRO MODELO"
@app_flask.route('/fotos/<path:filename>')
def foto(filename): return send_from_directory(PASTA_FOTOS, filename)
@app_flask.route('/mascaras/<path:filename>')
def masc(filename): return send_from_directory(PASTA_MASCARAS, filename)
@app_flask.route('/apagar/<chapa>')
def apagar_chapa_url(chapa):
    chapa = chapa.strip().zfill(6)
    apagados = apagar_tudo_da_chapa(chapa)
    return f"<h2>Chapa {chapa} apagada - {apagados['inventario']} registros</h2><a href=/base>Voltar</a>"
@app_flask.route('/apagar_chapa', methods=['GET','POST'])
def apagar_chapa_page():
    if request.method == 'POST':
        chapa = request.form.get('chapa','').strip().zfill(6)
        apagados = apagar_tudo_da_chapa(chapa)
        return f"<h2>Chapa {chapa} apagada</h2><a href=/base>Voltar</a>"
    return """<html><head><meta charset='utf-8'></head><body><form method='POST'>CHAPA: <input name='chapa' required><button>APAGAR</button></form><a href=/base>Voltar</a></body></html>"""
@app_flask.route('/atualizar_base', methods=['GET','POST'])
def atualizar_base():
    if request.method == 'POST':
        file = request.files['arquivo']; file.save(ARQ_FUNC)
        return f"<h2>Base atualizada</h2><a href=/base>Ver Base</a>"
    return """<form method='POST' enctype='multipart/form-data'><input type='file' name='arquivo' accept='.csv' required><button>ATUALIZAR</button></form>"""
@app_flask.route('/base')
def base():
    chapa_filtro = request.args.get('chapa','').strip()
    html = f"""<html><head><meta charset='utf-8'><style>body{{font-family:Arial;padding:20px}} table{{width:100%;border-collapse:collapse}} th,td{{padding:8px;border:1px solid #ddd}} th{{background:#0F3057;color:white}} .foto-padrao{{width:60px;height:60px;object-fit:cover;border-radius:6px;border:1px solid #ccc;margin:2px}} .foto-padrao:hover{{transform:scale(3);z-index:100;position:relative}}</style></head><body><h2>BASE FOTOS - ESTILOSA</h2><form method='GET'>CHAPA: <input name='chapa' value='{chapa_filtro}'><button>BUSCAR</button><a href='/base'><button type='button'>LIMPAR</button></a></form><table><tr><th>DATA</th><th>CHAPA</th><th>NOME</th><th>TEL</th><th>MAQ</th><th>OTDR</th><th>FOTOS MAQ</th><th>FOTOS OTDR</th><th>MASCARA</th><th>AÇÃO</th></tr>"""
    try:
        with open(ARQ_INV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if chapa_filtro and r.get('chapa','').zfill(6) != chapa_filtro.zfill(6): continue
                f_maq = "".join([f"<a href=/{r.get(k,'')} target=_blank><img class='foto-padrao' src=/{r.get(k,'')}></a>" for k in ["foto_maquina1","foto_maquina2","foto_maquina3"] if r.get(k)])
                f_otdr = "".join([f"<a href=/{r.get(k,'')} target=_blank><img class='foto-padrao' src=/{r.get(k,'')}></a>" for k in ["foto_otdr1","foto_otdr2","foto_otdr3"] if r.get(k)])
                masc = f"<a href=/{r.get('mascara_arquivo','')} target=_blank><img class='foto-padrao' src=/{r.get('mascara_arquivo','')}></a>" if r.get('mascara_arquivo') else "-"
                html+=f"<tr><td>{r.get('data_registro')}</td><td><b>{r.get('chapa')}</b></td><td>{r.get('nome')}</td><td>{r.get('telefone')}</td><td>{r.get('patrimonio_maquina')}</td><td>{r.get('patrimonio_otdr')}</td><td>{f_maq}</td><td>{f_otdr}</td><td>{masc}</td><td><a href='/apagar/{r.get('chapa')}' style='background:#dc3545;color:white;padding:5px 8px;border-radius:4px;text-decoration:none'>APAGAR</a></td></tr>"
    except Exception as e: html+=f"<tr><td colspan=10>{e}</td></tr>"
    html+="</table></body></html>"
    return html
@app_flask.route('/exportar')
def exp(): return send_file(ARQ_INV, as_attachment=True)

def run_flask(): app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("📸 Sistema Fotos Patrimonio\nEnvie sua CHAPA:")
    return CHAPA
async def chapa_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa=update.message.text.strip().zfill(6)
    dados=buscar_na_base_mestra(chapa)
    if not dados: await update.message.reply_text(f"Chapa {chapa} nao existe"); return CHAPA
    cad=buscar_cadastro(chapa)
    if cad and cad.get("telefone"):
        context.user_data.update(cad)
        await update.message.reply_text(f"Bem vindo {cad['nome']}!\nPASSO 1: Digite PATRIMONIO da MAQUINA:")
        return MAQ_PAT
    context.user_data["chapa"]=chapa; context.user_data["dados_mestra"]=dados
    kb=[[KeyboardButton("📱 Compartilhar telefone", request_contact=True)]]
    await update.message.reply_text(f"CHAPA OK: {dados['nome']}\nCompartilhe telefone:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return TELEFONE
async def telefone_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tel_raw=update.message.contact.phone_number if update.message.contact else update.message.text
    tel=formatar_telefone(tel_raw)
    m=context.user_data["dados_mestra"]
    dados={"chapa": context.user_data["chapa"], "nome": m["nome"], "funcao": m["funcao"], "lider_imediato": m["lider"], "coordenador": m["coord"], "telefone": tel, "id_telegram": str(update.effective_user.id)}
    salvar_cadastro(dados); context.user_data.update(dados)
    await update.message.reply_text(f"Tel {tel} salvo!\nPASSO 1: Digite PATRIMONIO da MAQUINA:")
    return MAQ_PAT
async def baixar(update, context, prefixo):
    ph=update.message.photo[-1]; file=await context.bot.get_file(ph.file_id)
    nome=f"{prefixo}_{uuid.uuid4().hex[:6]}.jpg"; caminho=os.path.join(PASTA_FOTOS, nome)
    await file.download_to_drive(caminho); return caminho
async def maq_pat_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pat=update.message.text.strip().upper()
    if patrimonio_existe(pat): await update.message.reply_text(f"Pat {pat} ja existe! Outro:"); return MAQ_PAT
    context.user_data["pat_maquina"]=pat; await update.message.reply_text(f"MAQUINA {pat}\nPASSO 2: FOTO 1 da MAQUINA:"); return MAQ_F1
async def maq_f1_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return MAQ_F1
    context.user_data["maq_f1"]=await baixar(update, context, context.user_data["pat_maquina"]+"_MAQ1")
    await update.message.reply_text("Foto 1 OK! FOTO 2:"); return MAQ_F2
async def maq_f2_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return MAQ_F2
    context.user_data["maq_f2"]=await baixar(update, context, context.user_data["pat_maquina"]+"_MAQ2")
    await update.message.reply_text("Foto 2 OK! FOTO 3:"); return MAQ_F3
async def maq_f3_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return MAQ_F3
    context.user_data["maq_f3"]=await baixar(update, context, context.user_data["pat_maquina"]+"_MAQ3")
    await update.message.reply_text("MAQUINA OK!\nPASSO 5: PATRIMONIO do OTDR:"); return OTDR_PAT
async def otdr_pat_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pat=update.message.text.strip().upper()
    if pat==context.user_data.get("pat_maquina"): await update.message.reply_text("OTDR != MAQUINA! Outro:"); return OTDR_PAT
    if patrimonio_existe(pat): await update.message.reply_text(f"Pat {pat} ja existe! Outro:"); return OTDR_PAT
    context.user_data["pat_otdr"]=pat; await update.message.reply_text(f"OTDR {pat}\nFOTO 1 do OTDR:"); return OTDR_F1
async def otdr_f1_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return OTDR_F1
    context.user_data["otdr_f1"]=await baixar(update, context, context.user_data["pat_otdr"]+"_OTDR1")
    await update.message.reply_text("Foto 1 OTDR OK! FOTO 2:"); return OTDR_F2
async def otdr_f2_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return OTDR_F2
    context.user_data["otdr_f2"]=await baixar(update, context, context.user_data["pat_otdr"]+"_OTDR2")
    await update.message.reply_text("Foto 2 OK! FOTO 3:"); return OTDR_F3
async def otdr_f3_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return OTDR_F3
    context.user_data["otdr_f3"]=await baixar(update, context, context.user_data["pat_otdr"]+"_OTDR3")
    kb=[[KeyboardButton("✅ FINALIZAR E GERAR MASCARA")]]
    await update.message.reply_text(f"RESUMO:\nMAQ: {context.user_data['pat_maquina']}\nOTDR: {context.user_data['pat_otdr']}\nFinalizar?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)); return FINAL
async def final_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "CANCELAR" in update.message.text.upper(): await update.message.reply_text("Cancelado. /start"); return ConversationHandler.END
    masc_txt, masc_png, texto_masc = gerar_mascara(context.user_data)
    data_reg = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    with open(ARQ_INV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([data_reg, context.user_data["chapa"], context.user_data["nome"], context.user_data["funcao"], context.user_data["lider_imediato"], context.user_data["coordenador"], context.user_data["telefone"], "KIT MAQ+OTDR", context.user_data["pat_maquina"], context.user_data["pat_otdr"], context.user_data["maq_f1"], context.user_data["maq_f2"], context.user_data["maq_f3"], context.user_data["otdr_f1"], context.user_data["otdr_f2"], context.user_data["otdr_f3"], masc_png])
    await update.message.reply_text(f"✅ SALVO!\n\n{texto_masc}")
    await context.bot.send_document(chat_id=update.effective_chat.id, document=open(masc_txt, "rb"), filename=os.path.basename(masc_txt))
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=open(masc_png, "rb"), caption=f"MASCARA {context.user_data['pat_maquina']} + {context.user_data['pat_otdr']}")
    await update.message.reply_text("Para novo KIT /start")
    return ConversationHandler.END
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("Cancelado. /start"); return ConversationHandler.END

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    try: asyncio.set_event_loop(asyncio.new_event_loop())
    except: pass
    application = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(entry_points=[CommandHandler("start", start)], states={CHAPA: [MessageHandler(filters.TEXT & ~filters.COMMAND, chapa_step)], TELEFONE: [MessageHandler(filters.ALL, telefone_step)], MAQ_PAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, maq_pat_step)], MAQ_F1: [MessageHandler(filters.PHOTO, maq_f1_step)], MAQ_F2: [MessageHandler(filters.PHOTO, maq_f2_step)], MAQ_F3: [MessageHandler(filters.PHOTO, maq_f3_step)], OTDR_PAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, otdr_pat_step)], OTDR_F1: [MessageHandler(filters.PHOTO, otdr_f1_step)], OTDR_F2: [MessageHandler(filters.PHOTO, otdr_f2_step)], OTDR_F3: [MessageHandler(filters.PHOTO, otdr_f3_step)], FINAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, final_step)]}, fallbacks=[CommandHandler("cancel", cancel)])
    application.add_handler(conv)
    print(">>> BOT FOTOS ON - PRIMEIRO")
    application.run_polling(drop_pending_updates=True)

if __name__=="__main__": main()
