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
    except Exception as e: print(f"Erro base: {e}")
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

# ===== MASCARA ESTILOSA MENOR 950x480 IGUAL PREVIEW =====
def gerar_mascara(dados):
    data_str = datetime.datetime.now().strftime("%d/%m/%Y")
    data_hora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    texto = f"MASCARA {dados['pat_maquina']} + {dados['pat_otdr']} | CHAPA {dados['chapa']} | {dados['nome']} | {data_hora}"
    try:
        os.makedirs(PASTA_MASCARAS, exist_ok=True)
        nome_base = f"{dados['pat_maquina']}_{dados['pat_otdr']}_{uuid.uuid4().hex[:4]}"
        caminho_txt = os.path.join(PASTA_MASCARAS, f"{nome_base}.txt")
        caminho_png = os.path.join(PASTA_MASCARAS, f"{nome_base}.png")
        with open(caminho_txt, "w", encoding="utf-8") as f: 
            f.write(f"MASCARA PATRIMONIO\nMAQUINA:{dados['pat_maquina']} OTDR:{dados['pat_otdr']}\nCHAPA:{dados['chapa']} NOME:{dados['nome']} TEL:{dados['telefone']}\nLIDER:{dados['lider_imediato']} COORD:{dados.get('coordenador','')}\nDATA:{data_hora}\nID:{nome_base}")

        W, H = 950, 480
        img = Image.new('RGB', (W, H), (255,255,255))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        def bold(x,y,t,c):
            draw.text((x,y),t,fill=c,font=font)
            draw.text((x+1,y),t,fill=c,font=font)

        # Header preto premium
        draw.rounded_rectangle([(0,0),(W,65)], radius=18, fill=(15,23,42))
        draw.rectangle([(0,40),(W,65)], fill=(15,23,42))
        draw.rectangle([(0,62),(W,67)], fill=(56,189,248)) # linha neon
        bold(22,15,"PATRIMONIO - KIT FUSAO + OTDR",(255,255,255))
        draw.text((W-170,22), f"DATA: {data_str}", fill=(255,255,255), font=font)

        # MAQUINA azul claro
        draw.rounded_rectangle([(18,80),(462,255)], radius=18, fill=(219,234,254), outline=(191,219,254), width=1)
        draw.text((30,95),"MAQUINA FUSAO", fill=(37,99,235), font=font)
        bold(30,108,"MAQUINA FUSAO",(37,99,235))
        draw.text((30,135),"PATRIMONIO:", fill=(100,116,139), font=font)
        bold(30,155, f"{dados['pat_maquina'][:18]}", (15,23,42))
        draw.text((30,190),"• ATIVO / OPERACIONAL", fill=(22,101,52), font=font)

        # OTDR laranja claro
        draw.rounded_rectangle([(488,80),(932,255)], radius=18, fill=(255,237,213), outline=(254,215,170), width=1)
        draw.text((500,95),"OTDR", fill=(234,88,12), font=font)
        bold(500,108,"OTDR",(234,88,12))
        draw.text((500,135),"PATRIMONIO:", fill=(100,116,139), font=font)
        bold(500,155, f"{dados['pat_otdr'][:18]}", (15,23,42))
        draw.text((500,190),"• ATIVO / OPERACIONAL", fill=(22,101,52), font=font)

        # Pill preta amarela CHAPA
        draw.rounded_rectangle([(80,270),(870,315)], radius=22, fill=(0,0,0))
        txt_pill = f"CHAPA {dados['chapa']}  |  {dados['nome'][:25]}  |  {dados['funcao'][:15]} |  {dados['telefone']}"
        draw.text((110,283), txt_pill, fill=(250,204,21), font=font)
        bold(110,283, txt_pill, (250,204,21))

        # LIDER e COORD barras cinza
        draw.rounded_rectangle([(20,330),(700,363)], radius=15, fill=(241,245,249), outline=(203,213,225))
        draw.text((30,338), f"LIDER: {dados['lider_imediato'][:35]}", fill=(71,85,105), font=font)
        draw.rounded_rectangle([(20,372),(700,405)], radius=15, fill=(241,245,249), outline=(203,213,225))
        draw.text((30,380), f"COORD: {dados.get('coordenador','')[:35]}", fill=(71,85,105), font=font)

        # Footer preto com QR
        draw.rounded_rectangle([(0,415),(W,H)], radius=18, fill=(15,23,42))
        draw.rectangle([(0,415),(W,435)], fill=(15,23,42))
        draw.text((20,430), f"ID: {nome_base.upper()} - TELECOM - CONTROLE DE ATIVOS", fill=(200,200,200), font=font)
        # QR fake estiloso
        qr_x, qr_y = W-90, 425
        draw.rectangle([(qr_x-5,qr_y-5),(qr_x+65,qr_y+65)], fill=(255,255,255))
        for i in range(5):
            for j in range(5):
                if (i+j)%2==0 or (i==0 and j==0) or (i==4):
                    c = (0,0,0) if (i+j)%3==0 else (56,189,248)
                    draw.rectangle([qr_x+i*12, qr_y+j*12, qr_x+i*12+8, qr_y+j*12+8], fill=c)
        draw.text((qr_x-95,445),"SCANEIE PARA", fill=(200,200,200), font=font)
        draw.text((qr_x-95,458),"VER REGISTRO", fill=(200,200,200), font=font)

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
    except Exception as e: print(e)

app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "BOT ON - MASCARA ESTILOSA MENOR + TRAVA"
@app_flask.route('/fotos/<path:filename>')
def foto(filename): return send_from_directory(PASTA_FOTOS, filename)
@app_flask.route('/mascaras/<path:filename>')
def masc(filename): return send_from_directory(PASTA_MASCARAS, filename)
@app_flask.route('/apagar/<chapa>')
def apagar_chapa_url(chapa): apagar_tudo_da_chapa(chapa); return f"<script>alert('Chapa {chapa} apagada!'); window.location='/base';</script>"
@app_flask.route('/atualizar_base', methods=['GET','POST'])
def atualizar_base():
    if request.method == 'POST':
        file = request.files['arquivo']; file.save(ARQ_FUNC)
        return f"<h2>Base atualizada</h2><a href=/base>Ver Base</a>"
    return """<form method='POST' enctype='multipart/form-data'><input type='file' name='arquivo' accept='.csv' required><button>ATUALIZAR BASE</button></form>"""
@app_flask.route('/ver_func')
def ver_func():
    try:
        with open(ARQ_FUNC, encoding="utf-8-sig") as f: linhas=f.readlines(); return f"<h2>Funcionarios: {len(linhas)-1}</h2><pre>{''.join(linhas[:20])}</pre><a href=/base>Voltar</a>"
    except Exception as e: return str(e)
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
@app_flask.route('/exportar_winrar')
def exportar_winrar(): return exportar_zip()
@app_flask.route('/apagar_chapa', methods=['GET','POST'])
def apagar_chapa_page():
    if request.method == 'POST':
        chapa = request.form.get('chapa','').strip()
        if chapa: apagar_tudo_da_chapa(chapa)
        return f"<h2>Chapa {chapa} apagada! Pode cadastrar de novo.</h2><a href=/base>Voltar</a>"
    return """<html><head><meta charset='utf-8'></head><body><h2>APAGAR POR CHAPA</h2><form method='POST'>CHAPA: <input name='chapa' required><button>APAGAR TUDO</button></form><br><a href=/base>Voltar</a></body></html>"""
@app_flask.route('/base')
def base():
    chapa_filtro = request.args.get('chapa','').strip()
    html = f"""
    <html><head><meta charset='utf-8'><title>BASE FOTOS - ESTILOSA MENOR</title>
    <style>
    body{{font-family:Arial;padding:20px; background:#f5f6f8}}
    table{{width:100%;border-collapse:collapse; background:white}}
    th,td{{padding:10px 8px;border:1px solid #ddd; text-align:center; font-size:13px}}
    th{{background:#0F3057;color:white}}
    .foto-padrao{{width:55px;height:55px;object-fit:cover;border-radius:6px;border:1px solid #ccc;margin:2px}}
    .foto-padrao:hover{{transform:scale(3.5);z-index:100;position:relative}}
    .mascara-preview{{width:160px;height:80px;object-fit:cover;border-radius:10px;border:2px solid #0F172A; cursor:pointer; box-shadow:0 2px 8px rgba(0,0,0,0.15)}}
    .mascara-preview:hover{{transform:scale(2.2);z-index:100;position:relative; box-shadow:0 0 20px black}}
    .btn-apagar{{background:#dc3545;color:white;padding:6px 10px;border-radius:5px;text-decoration:none;font-weight:bold}}
    input{{padding:6px}} button{{padding:6px 12px; cursor:pointer}}
    </style></head><body>
    <h2>BASE FOTOS - MASCARA ESTILOSA MENOR - TRAVA 1 POR CHAPA</h2>
    <form method='GET' style='margin-bottom:15px'>
        CHAPA: <input name='chapa' value='{chapa_filtro}' placeholder='Digite a chapa'>
        <button type='submit'>BUSCAR</button>
        <a href='/base'><button type='button'>LIMPAR</button></a>
        <a href='/apagar_chapa' style='margin-left:20px'><button type='button' style='background:#ff9800;color:white'>APAGAR POR CHAPA</button></a>
        <a href='/ver_func' style='margin-left:10px'><button type='button'>VER FUNCIONARIOS</button></a>
    </form>
    <table><tr><th>DATA</th><th>CHAPA</th><th>NOME</th><th>TEL</th><th>MAQ</th><th>OTDR</th><th>FOTOS MAQ</th><th>FOTOS OTDR</th><th>MASCARA ESTILOSA</th><th>AÇÃO</th></tr>
    """
    try:
        with open(ARQ_INV, encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            if chapa_filtro: reader = [r for r in reader if chapa_filtro.zfill(6) in str(r.get('chapa','')).zfill(6) or chapa_filtro in str(r.get('chapa',''))]
            for r in reader:
                f_maq = "".join([f"<a href=/{r.get(k,'')} target=_blank><img class='foto-padrao' src=/{r.get(k,'')}></a>" for k in ["foto_maquina1","foto_maquina2","foto_maquina3"] if r.get(k) and os.path.exists(r.get(k,''))])
                f_otdr = "".join([f"<a href=/{r.get(k,'')} target=_blank><img class='foto-padrao' src=/{r.get(k,'')}></a>" for k in ["foto_otdr1","foto_otdr2","foto_otdr3"] if r.get(k) and os.path.exists(r.get(k,''))])
                if r.get('mascara_arquivo') and os.path.exists(r.get('mascara_arquivo','')):
                    masc = f"<a href=/{r.get('mascara_arquivo','')} target=_blank><img class='mascara-preview' src=/{r.get('mascara_arquivo','')} title='Clique para ver grande'></a>"
                else: masc = "-"
                html+=f"<tr><td>{r.get('data_registro','')}</td><td><b>{r.get('chapa','')}</b></td><td>{r.get('nome','')[:18]}</td><td>{r.get('telefone','')}</td><td>{r.get('patrimonio_maquina','')}</td><td>{r.get('patrimonio_otdr','')}</td><td>{f_maq or '-'}</td><td>{f_otdr or '-'}</td><td>{masc}</td><td><a class='btn-apagar' href='/apagar/{r.get('chapa','')}' onclick=\"return confirm('Apagar chapa {r.get('chapa','')}?')\">APAGAR</a></td></tr>"
            if not reader: html+=f"<tr><td colspan=10 style='padding:30px'>Nenhum registro. {f'Filtro {chapa_filtro} nao encontrado' if chapa_filtro else 'Aguardando cadastros.'}</td></tr>"
    except Exception as e: html+=f"<tr><td colspan=10>Erro: {e}</td></tr>"
    html+=f"</table><br><div style='margin-top:20px'><a href='/exportar' style='background:#0F3057;color:white;padding:10px 15px;border-radius:5px;text-decoration:none;margin-right:10px'>📄 Exportar CSV</a> <a href='/exportar_zip' style='background:#28a745;color:white;padding:10px 15px;border-radius:5px;text-decoration:none'>📦 Exportar ZIP / WinRar</a></div></body></html>"
    return html

def run_flask(): app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("📸 Sistema Fotos Patrimonio\nEnvie sua CHAPA:")
    return CHAPA

async def chapa_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa=update.message.text.strip().zfill(6)
    dados=buscar_na_base_mestra(chapa)
    if not dados: 
        await update.message.reply_text(f"❌ Chapa {chapa} nao existe na base")
        return CHAPA
    ja_cad, registro = chapa_ja_cadastrou(chapa)
    if ja_cad:
        await update.message.reply_text(
            f"⛔ CHAPA {chapa} JA CADASTRADA!\nMAQUINA: {registro.get('patrimonio_maquina','')}\nOTDR: {registro.get('patrimonio_otdr','')}\nDATA: {registro.get('data_registro','')}\n\nPara novo cadastro: /base > BUSCAR {chapa} > APAGAR > /start"
        )
        return ConversationHandler.END
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
    context.user_data["pat_maquina"]=pat; await update.message.reply_text(f"MAQUINA {pat}\nFOTO 1 da MAQUINA:"); return MAQ_F1
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
    await update.message.reply_text("MAQUINA OK!\nPATRIMONIO do OTDR:"); return OTDR_PAT
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
    if "CANCELAR" in update.message.text.upper():
        await update.message.reply_text("Cancelado. /start"); return ConversationHandler.END
    try:
        await update.message.reply_text("⏳ Gerando mascara estilosa...")
        masc_txt, masc_png, texto_masc = gerar_mascara(context.user_data)
        data_reg = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        with open(ARQ_INV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([data_reg, context.user_data["chapa"], context.user_data["nome"], context.user_data["funcao"], context.user_data["lider_imediato"], context.user_data["coordenador"], context.user_data["telefone"], "KIT MAQ+OTDR", context.user_data["pat_maquina"], context.user_data["pat_otdr"], context.user_data["maq_f1"], context.user_data["maq_f2"], context.user_data["maq_f3"], context.user_data["otdr_f1"], context.user_data["otdr_f2"], context.user_data["otdr_f3"], masc_png])
        await update.message.reply_text(f"✅ SALVO!\n\n{texto_masc}")
        if os.path.exists(masc_txt):
            with open(masc_txt, "rb") as doc: await context.bot.send_document(chat_id=update.effective_chat.id, document=doc, filename=os.path.basename(masc_txt))
        if masc_png and os.path.exists(masc_png):
            with open(masc_png, "rb") as photo: await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo, caption=f"🎨 MASCARA ESTILOSA {context.user_data['pat_maquina']} + {context.user_data['pat_otdr']}")
        await update.message.reply_text("Para novo KIT /start")
    except Exception as e:
        print(f"ERRO FINAL: {e}")
        await update.message.reply_text(f"❌ Erro: {e}\nTente /start")
    return ConversationHandler.END
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("Cancelado. /start"); return ConversationHandler.END

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    import asyncio
    try: asyncio.set_event_loop(asyncio.new_event_loop())
    except: pass
    application = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(entry_points=[CommandHandler("start", start)], states={CHAPA: [MessageHandler(filters.TEXT & ~filters.COMMAND, chapa_step)], TELEFONE: [MessageHandler(filters.ALL, telefone_step)], MAQ_PAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, maq_pat_step)], MAQ_F1: [MessageHandler(filters.PHOTO, maq_f1_step)], MAQ_F2: [MessageHandler(filters.PHOTO, maq_f2_step)], MAQ_F3: [MessageHandler(filters.PHOTO, maq_f3_step)], OTDR_PAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, otdr_pat_step)], OTDR_F1: [MessageHandler(filters.PHOTO, otdr_f1_step)], OTDR_F2: [MessageHandler(filters.PHOTO, otdr_f2_step)], OTDR_F3: [MessageHandler(filters.PHOTO, otdr_f3_step)], FINAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, final_step)]}, fallbacks=[CommandHandler("cancel", cancel)])
    application.add_handler(conv)
    print(">>> BOT ON - MASCARA ESTILOSA MENOR")
    application.run_polling(drop_pending_updates=True)

if __name__=="__main__": main()
