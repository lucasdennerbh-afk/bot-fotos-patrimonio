import os, threading, time, csv, datetime, re, uuid, zipfile
from flask import Flask, request, send_file, send_from_directory
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, ContextTypes, filters

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")

ARQ_FUNC = "funcionarios.csv"
ARQ_CAD = "cadastros_fotos.csv"
ARQ_INV = "inventario_fotos.csv"
PASTA_FOTOS = "fotos"

os.makedirs(PASTA_FOTOS, exist_ok=True)

for arq, header in [
    (ARQ_CAD, ["chapa","nome","funcao","lider_imediato","coordenador","telefone","id_telegram"]),
    (ARQ_INV, ["data_registro","chapa","nome","funcao","lider_imediato","coordenador","telefone","tipo_item","patrimonio","foto1","foto2","foto3","file_id1","file_id2","file_id3"]),
]:
    if not os.path.exists(arq):
        with open(arq, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

CHAPA, TELEFONE, MENU, TIPO, PATRIMONIO, FOTO1, FOTO2, FOTO3 = range(8)

def formatar_telefone(tel_raw):
    if not tel_raw: return ""
    nums = re.sub(r'\D', '', str(tel_raw))
    if nums.startswith('55') and len(nums) > 11: nums = nums[2:]
    if len(nums) > 11: nums = nums[-11:]
    if len(nums) < 10: return nums
    return f"{nums[:2]}-{nums[2:]}"

def buscar_na_base_mestra(chapa):
    try:
        chapa_6 = str(chapa).strip().zfill(6)
        chapa_sem_zero = str(int(chapa)) if str(chapa).strip().isdigit() else str(chapa).strip()
        with open(ARQ_FUNC, encoding="utf-8-sig") as f:
            primeira = f.readline(); f.seek(0)
            delim = ";" if ";" in primeira else ","
            reader = csv.DictReader(f, delimiter=delim)
            if reader.fieldnames:
                reader.fieldnames = [c.strip().lower().replace(" ", "_").replace("\ufeff","") for c in reader.fieldnames]
            def get_col(nomes):
                for n in nomes:
                    if n in reader.fieldnames: return n
                return None
            chapa_col = get_col(["chapa"]) or reader.fieldnames[0]
            nome_col = get_col(["nome_completo","funcionario","nome"])
            funcao_col = get_col(["funcao","cargo"])
            lider_col = get_col(["lider_imediato","lider","supervisor"])
            coord_col = get_col(["coordenador","coord"])
            for r in reader:
                val = str(r.get(chapa_col,"")).strip()
                if not val or val.lower()=="none": continue
                if val.zfill(6)==chapa_6 or val==str(chapa).strip() or val==chapa_sem_zero:
                    return {
                        "nome": str(r.get(nome_col,"")).strip().upper(),
                        "funcao": str(r.get(funcao_col,"")).strip().upper() if funcao_col else "",
                        "lider": str(r.get(lider_col,"")).strip().upper() if lider_col else "",
                        "coord": str(r.get(coord_col,"")).strip().upper() if coord_col else ""
                    }
    except Exception as e:
        print(f"Erro base mestra: {e}")
    return None

def buscar_cadastro(chapa):
    try:
        with open(ARQ_CAD, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["chapa"]==chapa: return r
    except: pass
    return None

def salvar_cadastro(dados):
    rows=[]
    try:
        with open(ARQ_CAD, encoding="utf-8") as f: rows=list(csv.DictReader(f))
    except: pass
    rows=[r for r in rows if r["chapa"]!=dados["chapa"]]
    rows.append(dados)
    with open(ARQ_CAD, "w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=["chapa","nome","funcao","lider_imediato","coordenador","telefone","id_telegram"])
        w.writeheader(); w.writerows(rows)

def patrimonio_existe(patrimonio):
    try:
        with open(ARQ_INV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["patrimonio"].strip().upper() == patrimonio.strip().upper():
                    return True
    except: pass
    return False

app_flask=Flask(__name__)
@app_flask.route('/')
def home(): return "BOT FOTOS PATRIMONIO ON"

@app_flask.route('/fotos/<path:filename>')
def servir_foto(filename):
    return send_from_directory(PASTA_FOTOS, filename)

@app_flask.route('/base')
def ver_base():
    filtro_chapa=request.args.get('chapa','')
    filtro_pat=request.args.get('patrimonio','')
    html=f"""
    <style>
    body{{font-family:Arial;padding:15px;background:#f5f5f5}}
    table{{border-collapse:collapse;width:100%;font-size:12px;background:white}}
    th{{background:#000;color:white;padding:10px;white-space:nowrap}}
    td{{padding:8px;border:1px solid #ddd;text-align:center;vertical-align:middle}}
    .btn{{padding:10px 15px;text-decoration:none;border-radius:5px;color:white;display:inline-block;margin:3px;font-size:13px;font-weight:bold}}
    .btn-green{{background:#28a745}} .btn-blue{{background:#007bff}} .btn-red{{background:#dc3545}} .btn-orange{{background:#ff9800}} .btn-purple{{background:#6f42c1}}
    img{{width:90px;height:90px;object-fit:cover;border-radius:5px;border:2px solid #000;margin:2px}}
    .fotos{{display:flex;gap:3px;justify-content:center}}
    .linha-maquina{{background:#e3f2fd}} .linha-otdr{{background:#fff3e0}}
    </style>
    <h2>📸 BASE FOTOS - POR COLABORADOR</h2>
    <form method=get style=margin-bottom:15px>
      CHAPA: <input name=chapa value='{filtro_chapa}' size=8> Patrimônio: <input name=patrimonio value='{filtro_pat}' size=10>
      <button class=btn-blue type=submit>Filtrar</button> <a href=/base>Limpar</a>
    </form>
    <a href=/exportar class="btn btn-green">📥 Exportar CSV</a>
    <a href=/exportar_rar class="btn btn-purple">📦 Baixar TODAS Fotos em ZIP/RAR</a>
    <a href=/base?limpar=1 class="btn btn-red" onclick="return confirm('Apagar TUDO?')">🗑️ Limpar Base</a>
    <br><br>
    <table>
    <tr><th>CHAPA</th><th>NOME</th><th>TELEFONE</th><th>3 FOTOS JUNTAS</th><th>Nº PATRIMÔNIO</th><th>TIPO</th><th>DATA</th></tr>
    """
    if request.args.get('limpar')=='1':
        with open(ARQ_INV, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["data_registro","chapa","nome","funcao","lider_imediato","coordenador","telefone","tipo_item","patrimonio","foto1","foto2","foto3","file_id1","file_id2","file_id3"])
        html+="<div style='background:#d4edda;padding:10px'>✅ Base limpa!</div>"

    try:
        colaboradores = {}
        with open(ARQ_INV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if not r.get("chapa"): continue
                if filtro_chapa and filtro_chapa not in r.get("chapa",""): continue
                if filtro_pat and filtro_pat.upper() not in r.get("patrimonio","").upper(): continue
                ch = r.get("chapa","")
                if ch not in colaboradores: colaboradores[ch] = []
                colaboradores[ch].append(r)

        for chapa, itens in colaboradores.items():
            # Ordena para mostrar Maquina primeiro depois OTDR
            itens.sort(key=lambda x: x.get("tipo_item",""))
            for item in itens:
                tipo = item.get("tipo_item","")
                classe = "linha-maquina" if "FUSAO" in tipo else "linha-otdr"
                f1 = f"<a href=/{item.get('foto1','')} target=_blank><img src=/{item.get('foto1','')}></a>" if item.get('foto1') and os.path.exists(item.get('foto1','')) else "❌"
                f2 = f"<a href=/{item.get('foto2','')} target=_blank><img src=/{item.get('foto2','')}></a>" if item.get('foto2') and os.path.exists(item.get('foto2','')) else "❌"
                f3 = f"<a href=/{item.get('foto3','')} target=_blank><img src=/{item.get('foto3','')}></a>" if item.get('foto3') and os.path.exists(item.get('foto3','')) else "❌"
                html+=f"""
                <tr class='{classe}'>
                  <td><b>{item.get('chapa','')}</b></td>
                  <td>{item.get('nome','')}<br><small>{item.get('funcao','')}</small></td>
                  <td><b>{item.get('telefone','')}</b></td>
                  <td><div class='fotos'>{f1}{f2}{f3}</div></td>
                  <td style='font-size:15px'><b>{item.get('patrimonio','')}</b></td>
                  <td><b>{tipo}</b></td>
                  <td>{item.get('data_registro','')}</td>
                </tr>
                """
    except Exception as e:
        html+=f"<tr><td colspan=7>Erro: {e}</td></tr>"
    html+="</table><br><small>Azul = Máquina de Fusão | Laranja = OTDR</small>"
    return html

@app_flask.route('/exportar')
def exportar(): return send_file(ARQ_INV, as_attachment=True, download_name="inventario_fotos.csv")

@app_flask.route('/exportar_rar')
def exportar_rar():
    zip_path = "FOTOS_PATRIMONIO.zip"
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        if os.path.exists(ARQ_INV):
            zipf.write(ARQ_INV)
        try:
            with open(ARQ_INV, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    for key in ["foto1","foto2","foto3"]:
                        caminho = r.get(key,"")
                        if caminho and os.path.exists(caminho):
                            nome_no_zip = f"{r.get('chapa','')}_{r.get('nome','')}/{r.get('patrimonio','')}_{r.get('tipo_item','')}/{os.path.basename(caminho)}"
                            zipf.write(caminho, nome_no_zip)
        except Exception as e:
            print(e)
    return send_file(zip_path, as_attachment=True, download_name="FOTOS_PATRIMONIO.zip")

def run_flask(): app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Olá! Sistema de Fotos de Patrimônio\n\nEnvie sua CHAPA (6 dígitos):")
    return CHAPA

async def chapa_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa_raw=update.message.text.strip()
    if not chapa_raw.isdigit():
        await update.message.reply_text("CHAPA inválida, só números (6 dígitos):"); return CHAPA
    chapa=chapa_raw.zfill(6)
    dados_mestra=buscar_na_base_mestra(chapa)
    if not dados_mestra:
        await update.message.reply_text(f"⛔ CHAPA {chapa} NÃO EXISTE no banco!\nVerifique e tente novamente:"); return CHAPA
    cad=buscar_cadastro(chapa)
    if cad and cad.get("telefone"):
        context.user_data.update(cad)
        context.user_data["nome"]=cad["nome"]
        kb=[[KeyboardButton("🔧 Maquina de Fusão"), KeyboardButton("📡 OTDR")]]
        await update.message.reply_text(f"Bem vindo {cad['nome']}!\nFunção: {cad['funcao']}\n\nEscolha o item:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return MENU
    context.user_data["chapa"]=chapa
    context.user_data["dados_mestra"]=dados_mestra
    kb=[[KeyboardButton("📱 Compartilhar telefone", request_contact=True)]]
    await update.message.reply_text(f"✅ CHAPA ENCONTRADA:\n👤 {dados_mestra['nome']}\n💼 {dados_mestra['funcao']}\n👨‍💼 Líder: {dados_mestra['lider']}\n👔 Coord: {dados_mestra['coord']}\n\nCompartilhe seu telefone:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return TELEFONE

async def telefone_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tel_raw=update.message.contact.phone_number if update.message.contact else update.message.text.strip()
    tel=formatar_telefone(tel_raw)
    if len(re.sub(r'\D','',tel)) < 10:
        await update.message.reply_text("Telefone inválido! Envie com DDD ou clique em compartilhar:"); return TELEFONE
    m=context.user_data["dados_mestra"]
    dados={"chapa": context.user_data["chapa"],"nome": m["nome"],"funcao": m["funcao"],"lider_imediato": m["lider"],"coordenador": m["coord"],"telefone": tel,"id_telegram": str(update.effective_user.id)}
    salvar_cadastro(dados)
    context.user_data.update(dados)
    kb=[[KeyboardButton("🔧 Maquina de Fusão"), KeyboardButton("📡 OTDR")]]
    await update.message.reply_text(f"✅ Cadastro feito!\n📱 Tel: {tel}\n\nEscolha o item:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return MENU

async def menu_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto=update.message.text.strip().upper()
    if "FUSÃO" in texto or "FUSAO" in texto: context.user_data["tipo_item"]="MAQUINA DE FUSAO"
    elif "OTDR" in texto: context.user_data["tipo_item"]="OTDR"
    else: await update.message.reply_text("Escolha: 🔧 Maquina de Fusão ou 📡 OTDR"); return MENU
    await update.message.reply_text(f"Você escolheu: {context.user_data['tipo_item']}\n\nDigite o NÚMERO DE PATRIMÔNIO:", reply_markup={"remove_keyboard": True})
    return PATRIMONIO

async def patrimonio_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    patrimonio=update.message.text.strip().upper()
    if len(patrimonio) < 3:
        await update.message.reply_text("Patrimônio inválido, digite novamente:"); return PATRIMONIO
    if patrimonio_existe(patrimonio):
        await update.message.reply_text(f"⛔ Patrimônio {patrimonio} JÁ CADASTRADO! Não pode duplicar.\n\nDigite outro:"); return PATRIMONIO
    context.user_data["patrimonio"]=patrimonio
    await update.message.reply_text(f"Patrimônio {patrimonio} OK! ✅\n\nEnvie a FOTO 1 (tem que aparecer o número do patrimônio):")
    return FOTO1

async def baixar_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo=update.message.photo[-1]
    file=await context.bot.get_file(photo.file_id)
    nome_arq=f"{context.user_data['patrimonio']}_{uuid.uuid4().hex[:6]}.jpg"
    caminho=os.path.join(PASTA_FOTOS, nome_arq)
    await file.download_to_drive(caminho)
    return caminho, photo.file_id

async def foto1_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: await update.message.reply_text("Envie uma FOTO!"); return FOTO1
    nome, fid=await baixar_foto(update, context)
    context.user_data["foto1"]=nome; context.user_data["fid1"]=fid
    await update.message.reply_text("Foto 1 OK! ✅\n\nAgora envie a FOTO 2:"); return FOTO2

async def foto2_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: await update.message.reply_text("Envie uma FOTO!"); return FOTO2
    nome, fid=await baixar_foto(update, context)
    context.user_data["foto2"]=nome; context.user_data["fid2"]=fid
    await update.message.reply_text("Foto 2 OK! ✅\n\nAgora envie a FOTO 3 (última):"); return FOTO3

async def foto3_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: await update.message.reply_text("Envie uma FOTO!"); return FOTO3
    nome, fid=await baixar_foto(update, context)
    context.user_data["foto3"]=nome; context.user_data["fid3"]=fid
    with open(ARQ_INV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            context.user_data["chapa"],context.user_data["nome"],context.user_data["funcao"],
            context.user_data["lider_imediato"],context.user_data["coordenador"],context.user_data["telefone"],
            context.user_data["tipo_item"],context.user_data["patrimonio"],
            context.user_data["foto1"],context.user_data["foto2"],context.user_data["foto3"],
            context.user_data["fid1"],context.user_data["fid2"],context.user_data["fid3"],
        ])
    kb=[[KeyboardButton("🔧 Maquina de Fusão"), KeyboardButton("📡 OTDR")]]
    await update.message.reply_text(f"✅✅✅ SALVO!\n\n📦 {context.user_data['tipo_item']}\n🔢 Patrimônio: {context.user_data['patrimonio']}\n\nCadastre outro:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado. /start"); return ConversationHandler.END

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    while True:
        try:
            app=ApplicationBuilder().token(TOKEN).build()
            conv=ConversationHandler(
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
            app.add_handler(conv)
            print(">>> BOT FOTOS ON"); app.run_polling(drop_pending_updates=True)
        except Exception as e:
            print(f"CRASH: {e}"); time.sleep(5)

if __name__=="__main__": main()
