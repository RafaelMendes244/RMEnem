# ===================================================================
# RM ENEM SIMULADOR - ARQUIVO PRINCIPAL DA APLICAÇÃO FLASK
# ===================================================================

# --- 1. Imports de Bibliotecas ---
import os
import requests
import json
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, g, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
import openai
import anthropic
import psycopg2
from psycopg2.extras import RealDictCursor
from flask_mail import Mail, Message
import smtplib
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail as SendGridMail
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
import ssl
import certifi

# --- 1. Inicialização e Configuração ---
load_dotenv()

# Configuração SSL para usar certificados do certifi
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

ENEM_API_BASE_URL = 'https://enem-api-gules.vercel.app/v1'
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
except Exception as e:
    print(f"AVISO: Chave da API do Gemini não configurada. Erro: {e}")

questions_cache = {}

# --- Configuração do Flask-Mail ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
mail = Mail(app)

# --- Configuração do URLSafeTimedSerializer para verificação de e-mail ---
mail = Mail(app)
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# NOVO: Redirecionamento de Domínio Antigo para o Domínio Principal
@app.before_request
def redirect_old_domain():
    # Redireciona o domínio .onrender.com para o domínio profissional (https://www.rmsimulador.com.br)
    if request.host == 'rmsimulador.onrender.com':
        # Usa request.full_path para manter qualquer rota (ex: /login) no redirecionamento
        return redirect("https://www.rmsimulador.com.br" + request.full_path, code=301)

    # Opcional, mas recomendado para SEO: Redirecionar 'rmsimulador.com.br' para 'www.rmsimulador.com.br'
    # Isso garante que seu domínio canônico (principal) seja sempre com 'www'
    if request.host == 'rmsimulador.com.br':
        return redirect("https://www.rmsimulador.com.br" + request.full_path, code=301)

# --- 2. Gerenciamento de Banco de Dados (PostgreSQL) ---
def get_db_connection():
    if 'db' not in g:
        try:
            g.db = psycopg2.connect(os.getenv('DATABASE_URL'), cursor_factory=RealDictCursor)
        except psycopg2.Error as e:
            app.logger.error(f"Erro ao conectar ao PostgreSQL: {e}")
            raise
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY, 
                email TEXT UNIQUE NOT NULL, 
                password TEXT NOT NULL, 
                name TEXT,
                is_verified BOOLEAN NOT NULL DEFAULT FALSE
            )''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS simulados (
                id SERIAL PRIMARY KEY, 
                user_email TEXT NOT NULL, 
                prova_year TEXT NOT NULL, 
                duracao_segundos INTEGER,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, 
                FOREIGN KEY (user_email) REFERENCES users (email)
            )''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS respostas_simulado (
                id SERIAL PRIMARY KEY, 
                simulado_id INTEGER NOT NULL, 
                question_unique_id TEXT NOT NULL,
                user_answer TEXT NOT NULL, 
                FOREIGN KEY (simulado_id) REFERENCES simulados (id)
            )''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS redacoes (
                id SERIAL PRIMARY KEY, 
                user_email TEXT NOT NULL, 
                tema TEXT NOT NULL, 
                texto_redacao TEXT NOT NULL,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, 
                nota_total INTEGER, 
                nota_c1 INTEGER, 
                nota_c2 INTEGER,
                nota_c3 INTEGER, 
                nota_c4 INTEGER, 
                nota_c5 INTEGER, 
                feedback TEXT,
                FOREIGN KEY (user_email) REFERENCES users (email)
            )''')
        conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        app.logger.error(f"Erro ao criar tabelas: {e}")
        raise
    finally:
        cur.close()
    print("Banco de dados PostgreSQL inicializado com sucesso.")

# --- 4. Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Você precisa estar logado para acessar esta página.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Funçoes para ENVIAR para um DOS DOIS EMAILS
def send_email(recipient, subject, html_body):
    # Tenta enviar com Flask-Mail (Gmail) primeiro
    try:
        msg = Message(subject,
                    sender=('RM ENEM Simulador', app.config['MAIL_USERNAME']),
                    recipients=[recipient],
                    html=html_body)
        mail.send(msg)
        print(f"E-mail para {recipient} enviado com sucesso via Gmail.")
        return True
    except Exception as e:
        app.logger.error(f"FALHA NO ENVIO COM GMAIL: {e}. Tentando SendGrid...")
        # Se o Gmail falhar, tenta com SendGrid
        try:
            from_email = ('rafinha.break07@gmail.com', 'RM ENEM Simulador') # Use seu e-mail verificado no SendGrid aqui
            message = SendGridMail(
                from_email=from_email,
                to_emails=recipient,
                subject=subject,
                html_content=html_body
            )
            
            # Configuração SSL explícita para SendGrid
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
            response = sg.send(message)
            
            if response.status_code >= 200 and response.status_code < 300:
                print(f"E-mail para {recipient} enviado com sucesso via SendGrid.")
                return True
            else:
                app.logger.error(f"FALHA NO SENDGRID (STATUS CODE): {response.status_code} - {response.body}")
                return False
        except Exception as sg_e:
            app.logger.error(f"FALHA NO ENVIO COM SENDGRID: {sg_e}")
            return False

# --- 5. Funções Auxiliares ---
def get_questions_from_api_with_cache(year):
    if year in questions_cache: return questions_cache[year]
    try:
        response = requests.get(f'{ENEM_API_BASE_URL}/exams/{year}/questions?limit=180')
        response.raise_for_status()
        data = response.json().get('questions', [])
        questions_cache[year] = data
        return data
    except Exception as e:
        app.logger.error(f"Erro ao buscar questões para o ano {year}: {e}")
        return None

def format_duration(seconds):
    if seconds is None: return "N/A"
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

# --- 6. Rotas de Autenticação ---
@app.route("/")
def index():
    return render_template('index.html', user=session.get('user'))

@app.route("/login")
def login():
    if 'user' in session: return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/login/email', methods=['POST'])
def login_email():
    email = request.form['email']
    password = request.form['password']
    
    conn = get_db_connection()
    cur = conn.cursor()
    # CORREÇÃO: Usa %s em vez de ?
    cur.execute('SELECT * FROM users WHERE email = %s', (email,))
    user = cur.fetchone()
    cur.close()
    
    if not user:
        flash('Usuário não cadastrado.', 'danger')
    elif not user['is_verified']:
        flash('Sua conta ainda não foi verificada. Por favor, verifique seu e-mail.', 'warning')
    elif not check_password_hash(user['password'], password):
        flash('Senha incorreta.', 'danger')
    else:
        session['user'] = {'email': user['email'], 'name': user['name'] or user['email'].split('@')[0]}
        return redirect(url_for('index'))
    
    return redirect(url_for('login'))

@app.route('/register', methods=['POST'])
def register():
    # 1. Pega os dados do formulário
    email = request.form['email']
    password = request.form['password']
    name = request.form.get('name', '').strip()

    # 2. Faz as validações dos campos
    if not name or len(name) < 3 or not name.replace(' ', '').isalpha():
        flash('Por favor, insira um nome válido (pelo menos 3 letras, sem números ou caracteres especiais).', 'danger')
        return redirect(url_for('login'))

    if len(password) < 6:
        flash('A senha deve ter pelo menos 6 caracteres.', 'danger')
        return redirect(url_for('login'))
    
    # 3. Interage com o banco de dados
    conn = get_db_connection() # Pega a conexão gerenciada pelo Flask
    cur = conn.cursor()
    
    # Verifica se o e-mail já existe
    cur.execute('SELECT * FROM users WHERE email = %s', (email,))
    if cur.fetchone():
        flash('Este email já está cadastrado. Por favor, tente fazer o login.', 'danger')
        cur.close()
        return redirect(url_for('login'))
    
    # Se não existe, cria o novo usuário
    hashed_password = generate_password_hash(password)
    cur.execute('INSERT INTO users (email, password, name) VALUES (%s, %s, %s)',
                (email, hashed_password, name))
    conn.commit() # Salva a alteração no banco
    cur.close()

    # 4. Envia o e-mail de confirmação
    try:
        token = s.dumps(email, salt='email-confirm')
        confirm_url = url_for('confirmar_email', token=token, _external=True)
        html = render_template('email_confirmacao.html', confirm_url=confirm_url)
        send_email(email, 'Confirme seu E-mail - RM ENEM Simulador', html)
        flash('Cadastro realizado! Um e-mail de confirmação foi enviado. Verifique sua caixa de entrada ou a pasta de spam.', 'success')
    except Exception as e:
        app.logger.error(f"Falha ao enviar e-mail de confirmação: {e}")
        flash('Cadastro realizado, mas houve uma falha ao enviar o e-mail de confirmação.', 'warning')

    return redirect(url_for('login'))

@app.route('/confirmar/<token>')
def confirmar_email(token):
    try:
        email = s.loads(token, salt='email-confirm', max_age=3600)
    except SignatureExpired:
        flash('O link de confirmação expirou. Por favor, tente se cadastrar novamente.', 'danger')
        return redirect(url_for('login'))
    except Exception:
        flash('O link de confirmação é inválido ou já foi usado.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    # CORREÇÃO: Usa %s em vez de ?
    cur.execute('UPDATE users SET is_verified = TRUE WHERE email = %s', (email,))
    conn.commit()
    cur.close()

    flash('Sua conta foi verificada com sucesso! Você já pode fazer o login.', 'success')
    return redirect(url_for('login'))

@app.route('/esqueci-senha', methods=['GET', 'POST'])
def esqueci_senha_page():
    if 'user' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        cur.close()

        # Por segurança, mostramos a mesma mensagem mesmo que o e-mail não exista
        if user:
            # A lógica para gerar o token e o corpo do e-mail continua a mesma
            token = s.dumps(email, salt='password-reset-salt')
            reset_url = url_for('redefinir_senha_page', token=token, _external=True)
            html = render_template('email_redefinir_senha.html', reset_url=reset_url)
            
            send_email(email, 'Redefinição de Senha - RM ENEM Simulador', html)
        
        flash('Se o seu e-mail estiver em nosso sistema, um link para redefinir sua senha foi enviado. Verifique sua caixa de entrada ou a pasta de spam.', 'success')
        return redirect(url_for('login'))

    return render_template('esqueci_senha.html')

@app.route('/redefinir-senha/<token>', methods=['GET', 'POST'])
def redefinir_senha_page(token):
    if 'user' in session:
        return redirect(url_for('index'))
        
    try:
        # Valida o token e extrai o e-mail. Expira em 3600 segundos (1 hora)
        email = s.loads(token, salt='password-reset-salt', max_age=3600)
    except SignatureExpired:
        flash('O link de redefinição de senha expirou. Por favor, solicite um novo.', 'danger')
        return redirect(url_for('esqueci_senha_page'))
    except Exception:
        flash('O link de redefinição de senha é inválido ou já foi usado.', 'danger')
        return redirect(url_for('esqueci_senha_page'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('As senhas não coincidem.', 'danger')
            # Retorna para a mesma página para o usuário tentar de novo, mantendo o token na URL
            return render_template('redefinir_senha.html', token=token)

        if len(password) < 6:
            flash('A nova senha deve ter pelo menos 6 caracteres.', 'danger')
            return render_template('redefinir_senha.html', token=token)

        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('UPDATE users SET password = %s WHERE email = %s', (hashed_password, email))
        conn.commit()
        cur.close()

        flash('Sua senha foi redefinida com sucesso! Você já pode fazer o login.', 'success')
        return redirect(url_for('login'))

    return render_template('redefinir_senha.html', token=token)

@app.route("/logout")
@login_required
def logout():
    session.pop('user', None)
    flash('Você foi desconectado com sucesso.', 'success')
    return redirect(url_for('index'))

@app.route('/reportar-bug')
def reportar_bug_page():
    return render_template('reportar_bug.html', user=session.get('user'))

@app.route('/obrigado')
def obrigado_page():
    return render_template('obrigado.html', user=session.get('user'))

@app.route('/apoie')
def apoie_page():
    return render_template('apoie.html', user=session.get('user'))

# --- 7. Rotas de Simulados ---
@app.route('/exame')
@login_required
def exame():
    user = session.get('user')
    return render_template('exame.html', user=user)

@app.route('/api/provas')
def get_provas():
    try:
        response = requests.get(f'{ENEM_API_BASE_URL}/exams')
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.RequestException as req_e:
        app.logger.error(f"Erro na requisição para API ENEM (provas): {req_e}")
        return jsonify({'error': f"Erro de rede ou API externa: {req_e}"}), 500
    except Exception as e:
        app.logger.error(f"Erro inesperado em get_provas: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/provas/<year>/questoes')
def get_questoes(year):
    try:
        response = requests.get(f'{ENEM_API_BASE_URL}/exams/{year}/questions')
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.RequestException as req_e:
        app.logger.error(f"Erro na requisição para API ENEM (questoes): {req_e}")
        return jsonify({'error': f"Erro de rede ou API externa: {req_e}"}), 500
    except Exception as e:
        app.logger.error(f"Erro inesperado em get_questoes: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/submit', methods=['POST'])
@login_required
def submit_answers():
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO simulados (user_email, prova_year, duracao_segundos) VALUES (%s, %s, %s) RETURNING id',
                (session['user']['email'], data.get('year'), data.get('duracaoSegundos')))
    simulado_id = cur.fetchone()['id']
    
    for q_title, u_answer in data.get('respostas', {}).items():
        cur.execute('INSERT INTO respostas_simulado (simulado_id, question_unique_id, user_answer) VALUES (%s, %s, %s)',
                (simulado_id, q_title, u_answer))
    conn.commit()
    cur.close()
    return jsonify({'success': True, 'redirect_url': url_for('resultado_detalhe', simulado_id=simulado_id)})

# --- 8. Rotas de Resultados e Histórico ---
@app.route('/historico')
@login_required
def historico():
    return render_template('historico.html', user=session.get('user'))

@app.route('/api/historico')
@login_required
def get_historico():
    user_email = session['user']['email']
    conn = get_db_connection()
    cur = conn.cursor()
    historico_data = {'simulados': [], 'redacoes': []}

    try:
        cur.execute(
            'SELECT id, prova_year, duracao_segundos, timestamp FROM simulados WHERE user_email = %s ORDER BY timestamp DESC', 
            (user_email,)
        )
        simulados_db = cur.fetchall()

        for s in simulados_db:
            cur.execute(
                'SELECT question_unique_id, user_answer FROM respostas_simulado WHERE simulado_id = %s', 
                (s['id'],)
            )
            respostas_db = cur.fetchall()
            
            user_respostas = {r['question_unique_id']: r['user_answer'] for r in respostas_db}
            total_respondidas = len(user_respostas)
            acertos = 0
            
            if total_respondidas > 0:
                questoes_api = get_questions_from_api_with_cache(s['prova_year'])
                if questoes_api:
                    for q_api in questoes_api:
                        if q_api.get('title') in user_respostas and user_respostas[q_api.get('title')] == q_api.get('correctAlternative'):
                            acertos += 1
            
            timestamp_obj = s['timestamp']
            
            historico_data['simulados'].append({
                'id': s['id'], 
                'prova_year': s['prova_year'],
                'timestamp': timestamp_obj.strftime('%d/%m/%Y %H:%M'),
                'duracao_formatada': format_duration(s['duracao_segundos']),
                'acertos': acertos, 
                'total_questoes_respondidas': total_respondidas
            })

        cur.execute(
            'SELECT id, tema, timestamp FROM redacoes WHERE user_email = %s ORDER BY timestamp DESC', 
            (user_email,)
        )
        redacoes_db = cur.fetchall()
        
        for r in redacoes_db:
            timestamp_obj = r['timestamp']
            historico_data['redacoes'].append({
                'id': r['id'],
                'tema': r['tema'],
                'timestamp': timestamp_obj.strftime('%d/%m/%Y')
            })
            
    except Exception as e:
        app.logger.error(f"Erro ao buscar histórico: {e}")
        return jsonify({'error': 'Falha ao carregar o histórico.'}), 500
    finally:
        cur.close()
            
    return jsonify(historico_data)

@app.route('/resultado/<int:simulado_id>')
@login_required
def resultado_detalhe(simulado_id):
    return render_template('resultado.html', user=session.get('user'), simulado_id=simulado_id)

@app.route('/api/resultado/<int:simulado_id>')
@login_required
def get_resultado_detalhado(simulado_id):
    user_email = session['user']['email']
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            'SELECT * FROM simulados WHERE id = %s AND user_email = %s',
            (simulado_id, user_email)
        )
        simulado = cur.fetchone()

        if not simulado:
            return jsonify({'error': 'Simulado não encontrado ou não pertence a este usuário.'}), 404

        cur.execute(
            'SELECT question_unique_id, user_answer FROM respostas_simulado WHERE simulado_id = %s',
            (simulado_id,)
        )
        respostas_db = cur.fetchall()
        user_respostas = {r['question_unique_id']: r['user_answer'] for r in respostas_db}
        
        prova_year = simulado['prova_year']
        todas_questoes_da_prova = get_questions_from_api_with_cache(prova_year)

        if not todas_questoes_da_prova:
            return jsonify({'error': f'Não foi possível obter o gabarito para a prova de {prova_year}.'}), 500

        acertos_totais = 0
        respostas_detalhadas = []

        for q_unique_id, user_answer in user_respostas.items():
            q_api = next((q for q in todas_questoes_da_prova if q.get('title') == q_unique_id), None)
            
            if q_api:
                acertou = (user_answer == q_api.get('correctAlternative'))
                if acertou:
                    acertos_totais += 1
                
                respostas_detalhadas.append({
                    'question_number': q_api.get('index'),
                    'question_context': q_api.get('context'),
                    'alternativesIntroduction': q_api.get('alternativesIntroduction'),
                    'files': q_api.get('files'),
                    'alternatives': q_api.get('alternatives'),
                    'discipline': q_api.get('discipline'),
                    'user_answer': user_answer,
                    'correct_answer': q_api.get('correctAlternative'),
                    'acertou': acertou
                })

        total_questoes_respondidas = len(user_respostas)
        porcentagem_total = (acertos_totais / total_questoes_respondidas) * 100 if total_questoes_respondidas > 0 else 0

        return jsonify({
            'prova_year': simulado['prova_year'],
            'timestamp': simulado['timestamp'].strftime('%d/%m/%Y %H:%M'),
            'duracao_segundos': simulado['duracao_segundos'],
            'acertos_totais': acertos_totais,
            'total_questoes': total_questoes_respondidas,
            'porcentagem_total': round(porcentagem_total, 2),
            'respostas_detalhadas': sorted(respostas_detalhadas, key=lambda x: x['question_number'])
        })
    except Exception as e:
        app.logger.error(f"Erro ao buscar resultado detalhado: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

# --- 9. Rotas de Redação ---
@app.route('/redacao')
@login_required
def redacao_page():
    return render_template('redacao.html', user=session.get('user'))

@app.route('/api/salvar_redacao', methods=['POST'])
@login_required
def salvar_redacao():
    data = request.get_json()
    tema = data.get('tema')
    texto_redacao = data.get('texto_redacao')
    user_email = session['user']['email']

    if not tema or not texto_redacao or len(texto_redacao) < 100:
        return jsonify({'error': 'Tema e texto da redação (mínimo 100 caracteres) são obrigatórios.'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            'INSERT INTO redacoes (user_email, tema, texto_redacao) VALUES (%s, %s, %s)',
            (user_email, tema, texto_redacao)
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Redação salva com sucesso!'})
    except Exception as e:
        app.logger.error(f"Erro ao salvar redação: {e}")
        return jsonify({'error': 'Ocorreu um erro ao salvar a redação.'}), 500
    finally:
        cur.close()

@app.route('/redacao/<int:redacao_id>')
@login_required
def ver_redacao(redacao_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            'SELECT * FROM redacoes WHERE id = %s AND user_email = %s',
            (redacao_id, session['user']['email'])
        )
        redacao_db = cur.fetchone()

        if not redacao_db:
            flash('Redação não encontrada ou não pertence a este usuário.', 'danger')
            return redirect(url_for('historico'))
        
        redacao = dict(redacao_db)
        redacao['timestamp_formatado'] = redacao['timestamp'].strftime('%d/%m/%Y às %H:%M')
        
        return render_template('ver_redacao.html', user=session.get('user'), redacao=redacao)
    finally:
        cur.close()

@app.route('/api/corrigir_redacao/<int:redacao_id>', methods=['POST'])
@login_required
def corrigir_redacao(redacao_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            'SELECT * FROM redacoes WHERE id = %s AND user_email = %s',
            (redacao_id, session['user']['email'])
        )
        redacao = cur.fetchone()

        if not redacao:
            return jsonify({'error': 'Redação não encontrada.'}), 404

        if redacao['feedback']:
            # Se já tem feedback, retorna o feedback existente
            return jsonify({
                'nota_total': redacao['nota_total'],
                'notas': [redacao['nota_c1'], redacao['nota_c2'], redacao['nota_c3'], 
                redacao['nota_c4'], redacao['nota_c5']],
                'feedback': redacao['feedback']
            })

        texto_redacao = redacao['texto_redacao']

        # --- 1. PROMPT BASE PARA TODAS AS APIS (adapte se for muito diferente) ---
        # Este prompt deve ser o mais universal possível para funcionar bem com todas as LLMs
        base_prompt = f"""
        Você é um corretor especialista em redações do ENEM com 10 anos de experiência. Está avaliando uma redação de um estudante que está se preparando para o ENEM 2025. 

        Siga RIGOROSAMENTE as diretrizes oficiais do MEC para correção, considerando as 5 competências:

        1. DOMÍNIO DA NORMA CULTA (0-200 pontos)
        - Avalie gramática, ortografia, pontuação e registro formal
        - Desconte pontos por erros recorrentes, mas reconheça acertos

        2. COMPREENSÃO DO TEMA (0-200 pontos)
        - Verifique se o texto aborda completamente o tema proposto
        - Avalie se há fuga parcial ou total ao tema
        - Considere a profundidade da abordagem

        3. ARGUMENTAÇÃO E ORGANIZAÇÃO (0-200 pontos)
        - Analise a estrutura do texto (introdução, desenvolvimento, conclusão)
        - Avalie a qualidade dos argumentos e a progressão temática
        - Verifique o uso de repertório sociocultural pertinente

        4. COESÃO E COERÊNCIA (0-200 pontos)
        - Avalie os mecanismos de coesão (conectivos, referências)
        - Verifique a coerência entre as partes do texto
        - Considere a organização lógica das ideias

        5. PROPOSTA DE INTERVENÇÃO (0-200 pontos)
        - Avalie se a proposta é detalhada e viável
        - Verifique se contempla agentes, ações, meios e efeitos
        - Considere a originalidade e pertinência da proposta

        INSTRUÇÕES PARA A CORREÇÃO:

        1. Seja rigoroso, mas pedagógico. Aponte erros, mas também destaque acertos.
        2. Atribua notas justas, considerando o nível de um estudante em preparação.
        3. Forneça justificativas detalhadas para cada competência.
        4. Inclua sugestões específicas de melhoria com exemplos.
        5. Formate sua resposta como JSON válido, sem texto adicional.

        ESTRUTURA DO JSON DE RESPOSTA:
            {{
            "nota_c1": <nota>,
            "nota_c2": <nota>,
            "nota_c3": <nota>,
            "nota_c4": <nota>,
            "nota_c5": <nota>,
            "nota_total": <nota_total>,
            "feedback": "<seu feedback em texto aqui>"
            }}

            REDAÇÃO PARA AVALIAR:
            ---
            {texto_redacao}
            ---
        """

        correcao_data = None
        api_usada = "Nenhuma"

        # --- 2. TENTAR API GEMINI (PRIMEIRA OPÇÃO) ---
        try:
            model = genai.GenerativeModel('gemini-1.5-flash-latest')
            response_gemini = model.generate_content(base_prompt) # Use o prompt específico da Gemini
            
            clean_response_gemini = response_gemini.text.replace('```json', '').replace('```', '').strip()
            correcao_data = json.loads(clean_response_gemini)
            api_usada = "Gemini"

        except Exception as e_gemini:
            app.logger.warning(f"Gemini API falhou ({e_gemini}). Tentando OpenAI como fallback.")
            
            # --- 3. TENTAR API OPENAI (SEGUNDA OPÇÃO - FALLBACK) ---
            try:
                openai.api_key = os.getenv("OPENAI_API_KEY") 

                response_openai = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo", 
                    messages=[
                        {"role": "system", "content": "Você é um corretor de redações ENEM e retorna APENAS JSON."},
                        {"role": "user", "content": base_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=1000 
                )
                
                openai_raw_text = response_openai.choices[0].message.content.strip()
                clean_response_openai = openai_raw_text.replace('```json', '').replace('```', '').strip()
                correcao_data = json.loads(clean_response_openai)
                api_usada = "OpenAI"

            except Exception as e_openai:
                app.logger.warning(f"OpenAI API falhou ({e_openai}). Tentando Anthropic (Claude) como fallback.")
                
                # --- 4. TENTAR API ANTHROPIC (TERCEIRA OPÇÃO - FALLBACK) ---
                try:
                    anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                    
                    # Para Anthropic, o formato da mensagem é um pouco diferente (usar messages API)
                    # e o modelo pode ser 'claude-3-haiku-20240307' ou 'claude-3-sonnet-20240229'
                    response_anthropic = anthropic_client.messages.create(
                        model="claude-3-haiku-20240307", # Escolha o modelo Claude
                        max_tokens=1000,
                        messages=[
                            {"role": "user", "content": base_prompt}
                        ]
                    )
                    
                    anthropic_raw_text = response_anthropic.content[0].text.strip()
                    clean_response_anthropic = anthropic_raw_text.replace('```json', '').replace('```', '').strip()
                    correcao_data = json.loads(clean_response_anthropic)
                    api_usada = "Anthropic"

                except Exception as e_anthropic:
                    # Se todas as APIs falharem
                    app.logger.error(f"Todas as APIs de IA falharam (Gemini, OpenAI, Anthropic): {e_anthropic}")
                    return jsonify({'error': 'Não foi possível obter a correção da IA no momento. Tente novamente mais tarde.'}), 500
        
        # --- 5. SE UMA API RETORNOU CORREÇÃO VÁLIDA, SALVAR E RETORNAR ---
        if correcao_data:
            cur.execute(
                '''UPDATE redacoes SET 
                nota_c1 = %s, nota_c2 = %s, nota_c3 = %s, nota_c4 = %s, nota_c5 = %s, nota_total = %s, feedback = %s
                WHERE id = %s''',
                (correcao_data['nota_c1'], correcao_data['nota_c2'], correcao_data['nota_c3'], 
                correcao_data['nota_c4'], correcao_data['nota_c5'], correcao_data['nota_total'], 
                correcao_data['feedback'], redacao_id)
            )
            conn.commit()
            
            resposta_final = {
                'nota_total': correcao_data['nota_total'],
                'notas': [correcao_data['nota_c1'], correcao_data['nota_c2'], correcao_data['nota_c3'], 
                        correcao_data['nota_c4'], correcao_data['nota_c5']],
                'feedback': correcao_data['feedback']
            }
            app.logger.info(f"Redação {redacao_id} corrigida com sucesso usando a API {api_usada}.")
            return jsonify(resposta_final)
        else:
            # Se correcao_data for None (o que não deve acontecer se as exceptions forem tratadas e retornadas corretamente)
            app.logger.error("API de IA retornou resposta inesperada ou nula.")
            return jsonify({'error': 'Não foi possível obter a correção da IA no momento (resposta inválida).'}), 500

    except Exception as e_geral:
        # Erro geral antes das chamadas de API ou de conexão com DB
        app.logger.error(f"Erro geral em corrigir_redacao: {e_geral}")
        return jsonify({'error': 'Ocorreu um erro inesperado ao tentar corrigir a redação.'}), 500
    finally:
        cur.close()

@app.route('/api/gerar_tema_aleatorio', methods=['GET'])
def gerar_tema_aleatorio():
    conn = get_db_connection()
    cur = conn.cursor()
    tema_gerado = None

    try:
        # Tenta buscar um tema aleatório do banco de dados
        cur.execute('SELECT tema_texto FROM temas_redacao ORDER BY RANDOM() LIMIT 1')
        result = cur.fetchone()

        if result:
            tema_gerado = result['tema_texto']
            return jsonify({'tema': tema_gerado})
        else:
            # Se não houver temas no banco de dados, gera um com a IA como fallback (ou retorna um tema padrão)
            app.logger.warning("Nenhum tema encontrado no banco de dados. Gerando com a API Gemini como fallback.")

            # CÓDIGO DA API GEMINI PARA GERAR TEMA (SE QUISER UM FALLBACK)
            prompt = """
            Aja como um especialista em vestibulares e crie um único tema de redação inédito e plausível para o ENEM 2025.
            O tema deve seguir o formato oficial, abordando um problema social, cultural ou científico relevante para o Brasil.
            Exemplos de formato: "Desafios para...", "O papel de...", "A questão de... na sociedade brasileira".
            Sua resposta deve ser APENAS o texto do tema, sem aspas, sem introduções como "Aqui está o tema:", apenas a frase do tema.
            """
            model = genai.GenerativeModel('gemini-1.5-flash-latest')
            response = model.generate_content(prompt)
            tema_gerado = response.text.strip()

            # Opcional: Salvar o tema gerado pela IA no banco de dados para uso futuro
            cur.execute('INSERT INTO temas_redacao (tema_texto) VALUES (%s) ON CONFLICT (tema_texto) DO NOTHING', (tema_gerado,))
            conn.commit() # Salva o novo tema

            return jsonify({'tema': tema_gerado})

    except Exception as e:
        app.logger.error(f"Erro ao gerar tema aleatório: {e}")
        # Retorna um tema padrão em caso de erro no DB ou na API Gemini
        return jsonify({'tema': 'O desafio dos resíduos plásticos nos oceanos e o seu impacto no futuro do planeta'}), 500
    finally:
        cur.close()

# --- 10. Rotas de Ranking ---
@app.route('/ranking')
def ranking_page():
    return render_template('ranking.html', user=session.get('user'))

@app.route('/api/ranking_geral')
def get_ranking_geral():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT * FROM simulados')
        simulados = cur.fetchall()
        
        cur.execute('SELECT email, name FROM users')
        usuarios = cur.fetchall()
        
        cur.execute('SELECT * FROM respostas_simulado')
        respostas = cur.fetchall()

        usuarios_dict = {u['email']: u['name'] for u in usuarios}
        respostas_por_simulado = {}
        for r in respostas:
            if r['simulado_id'] not in respostas_por_simulado:
                respostas_por_simulado[r['simulado_id']] = {}
            respostas_por_simulado[r['simulado_id']][r['question_unique_id']] = r['user_answer']

        ranking_temp = {}
        for s in simulados:
            user_email = s['user_email']
            user_respostas = respostas_por_simulado.get(s['id'], {})
            total_respondidas = len(user_respostas)

            if total_respondidas == 0:
                continue

            acertos = 0
            questoes_api = get_questions_from_api_with_cache(s['prova_year'])
            if questoes_api:
                for q_api in questoes_api:
                    q_unique_id = q_api.get('title')
                    if q_unique_id in user_respostas and user_respostas[q_unique_id] == q_api.get('correctAlternative'):
                        acertos += 1
            
            if user_email not in ranking_temp:
                ranking_temp[user_email] = {
                    'name': usuarios_dict.get(user_email, user_email),
                    'acertos_totais': 0, 'total_questoes': 0, 'duracoes': []
                }
            
            ranking_temp[user_email]['acertos_totais'] += acertos
            ranking_temp[user_email]['total_questoes'] += total_respondidas
            if s['duracao_segundos']:
                ranking_temp[user_email]['duracoes'].append(s['duracao_segundos'])

        ranking = []
        for user_email, dados in ranking_temp.items():
            if dados['total_questoes'] > 0:
                media_duracao = sum(dados['duracoes']) // len(dados['duracoes']) if dados['duracoes'] else 0
                ranking.append({
                    'name': dados['name'],
                    'porcentagem': round((dados['acertos_totais'] / dados['total_questoes']) * 100, 2),
                    'duracao_formatada': format_duration(media_duracao),
                    'acertos': dados['acertos_totais'],
                    'total_questoes': dados['total_questoes']
                })
        
        ranking.sort(key=lambda x: (-x['porcentagem'], x['duracao_formatada']))
        return jsonify(ranking[:50])

    except Exception as e:
        app.logger.error(f"Erro ao gerar ranking: {e}")
        return jsonify({'error': 'Falha ao gerar o ranking.'}), 500
    finally:
        cur.close()

# --- 11. Rotas de Administração ---
@app.route('/admin/view_db/<secret_key>')
def view_db(secret_key):
    admin_secret = os.getenv('ADMIN_SECRET_KEY')
    
    if not admin_secret or secret_key != admin_secret:
        return "Acesso não autorizado.", 403

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        tables = [table['table_name'] for table in cur.fetchall()]
        
        db_data = {}
        for table_name in tables:
            cur.execute(f"SELECT * FROM {table_name}")
            db_data[table_name] = cur.fetchall()
        
        return render_template('admin_view.html', db_data=db_data)
    except Exception as e:
        return f"Ocorreu um erro ao acessar o banco de dados: {e}"
    finally:
        cur.close()

# Rota para SEO
# Rota para o robots.txt
@app.route('/robots.txt')
def robots():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'robots.txt')

# Rota para o sitemap.xml
@app.route('/sitemap.xml')
def sitemap():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'sitemap.xml')

# Serve o arquivo de verificação diretamente da raiz
@app.route('/googlecfb1a13facc969a3.html')
def verify_google():
    return send_from_directory(os.path.join(app.root_path), 'googlecfb1a13facc969a3.html')

# --- 12. Execução da Aplicação ---
if __name__ == '__main__':
    # with app.app_context():
    #     init_db()
    app.run(debug=True)