# ===================================================================
# RM ENEM SIMULADOR - ARQUIVO PRINCIPAL DA APLICAÇÃO FLASK
# ===================================================================

# --- 1. Imports de Bibliotecas ---
import os
import requests
import sqlite3
import json
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# --- 2. Configuração da Aplicação ---
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# Configuração da API ENEM
ENEM_API_KEY = os.getenv('API_ENEM_KEY')
ENEM_API_BASE_URL = 'https://enem-api-gules.vercel.app/v1'

# Configuração da API Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Otimização: Cache em memória para as questões
questions_cache = {}

# --- 3. Configuração do Banco de Dados ---
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Modo Write-Ahead Logging
    conn.execute("PRAGMA busy_timeout=30000")  # Timeout de 30 segundos
    return conn

def with_db_connection(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        conn = None
        try:
            conn = get_db_connection()
            g.db = conn
            result = func(*args, **kwargs)
            conn.commit()
            return result
        except Exception as e:
            if conn:
                conn.rollback()
            app.logger.error(f"Database error: {e}")
            raise e
        finally:
            if conn:
                conn.close()
    return wrapper

def init_db():
    with app.app_context():
        conn = get_db_connection()
        conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT
        )
        ''')
        conn.execute('''
        CREATE TABLE IF NOT EXISTS simulados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            prova_year TEXT NOT NULL,
            duracao_segundos INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_email) REFERENCES users (email)
        )
        ''')
        conn.execute('''
        CREATE TABLE IF NOT EXISTS respostas_simulado (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            simulado_id INTEGER NOT NULL,
            question_unique_id TEXT NOT NULL,
            user_answer TEXT NOT NULL,
            FOREIGN KEY (simulado_id) REFERENCES simulados (id)
        )
        ''')
        conn.execute('''
        CREATE TABLE IF NOT EXISTS redacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            tema TEXT NOT NULL,
            texto_redacao TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            nota_total INTEGER,
            nota_c1 INTEGER,
            nota_c2 INTEGER,
            nota_c3 INTEGER,
            nota_c4 INTEGER,
            nota_c5 INTEGER,
            feedback TEXT,
            FOREIGN KEY (user_email) REFERENCES users (email)
        )
        ''')
        conn.commit()
        conn.close()

init_db()

# --- 4. Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Você precisa estar logado para acessar esta página.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- 5. Funções Auxiliares ---
def get_questions_from_api_with_cache(year):
    if year in questions_cache:
        return questions_cache[year]
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
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

# --- 6. Rotas de Autenticação ---
@app.route("/")
def index():
    user = session.get('user')
    return render_template('index.html', user=user)

@app.route("/login")
def login():
    if 'user' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/login/email', methods=['POST'])
def login_email():
    email = request.form['email']
    password = request.form['password']
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()
    
    if not user:
        flash('Usuário não cadastrado.', 'error')
    elif not check_password_hash(user['password'], password):
        flash('Senha Incorreta!', 'error')
    else:
        session['user'] = {
            'email': user['email'],
            'name': user['name'] or user['email'].split('@')[0]
        }
        flash('Login Efetuado com Sucesso.', 'success')
        return redirect(url_for('index'))
    
    return redirect(url_for('login'))

@app.route('/register', methods=['POST'])
@with_db_connection
def register():
    email = request.form['email']
    password = request.form['password']
    name = request.form.get('name', '')

    hashed_password = generate_password_hash(password)
    
    try:
        cursor = g.db.execute('SELECT 1 FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            flash('Este email já está cadastrado. Por favor, tente fazer o login.', 'error')
            return redirect(url_for('login'))

        g.db.execute('INSERT INTO users (email, password, name) VALUES (?, ?, ?)',
                    (email, hashed_password, name))
        
        session['user'] = {
            'email': email,
            'name': name or email.split('@')[0]
        }
        flash('Cadastro realizado com sucesso!', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        flash(f'Ocorreu um erro inesperado: {str(e)}', 'error')
        return redirect(url_for('login'))

@app.route("/logout")
def logout():
    session.pop('user', None)
    flash('Você foi desconectado com sucesso.', 'success')
    return redirect(url_for('index'))

@app.route('/reportar-bug')
def reportar_bug_page():
    # Passamos o 'user' para que o campo de email possa ser preenchido automaticamente se o usuário estiver logado
    return render_template('reportar_bug.html', user=session.get('user'))

@app.route('/obrigado')
def obrigado_page():
    # Esta rota apenas mostra a página de agradecimento
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
    year = data.get('year')
    user_respostas = data.get('respostas', {})
    duracao_segundos = data.get('duracaoSegundos')

    if not year or not user_respostas:
        return jsonify({'error': 'Dados de submissão incompletos'}), 400

    user_email = session['user']['email']
    
    try:
        conn = get_db_connection()
        cursor = conn.execute('''
            INSERT INTO simulados (user_email, prova_year, duracao_segundos)
            VALUES (?, ?, ?)
        ''', (user_email, year, duracao_segundos))
        simulado_id = cursor.lastrowid
        
        for question_unique_id, user_answer in user_respostas.items():
            conn.execute('''
                INSERT INTO respostas_simulado (simulado_id, question_unique_id, user_answer)
                VALUES (?, ?, ?)
            ''', (simulado_id, question_unique_id, user_answer))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'redirect_url': url_for('resultado_detalhe', simulado_id=simulado_id)})
    except Exception as e:
        app.logger.error(f"Erro ao salvar respostas: {e}")
        return jsonify({'error': str(e)}), 500

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
    historico_data = {'simulados': [], 'redacoes': []}

    try:
        simulados_db = conn.execute(
            'SELECT id, prova_year, duracao_segundos, timestamp FROM simulados WHERE user_email = ? ORDER BY timestamp DESC', 
            (user_email,)
        ).fetchall()

        for s in simulados_db:
            respostas_db = conn.execute(
                'SELECT question_unique_id, user_answer FROM respostas_simulado WHERE simulado_id = ?', 
                (s['id'],)
            ).fetchall()
            
            user_respostas = {r['question_unique_id']: r['user_answer'] for r in respostas_db}
            total_respondidas = len(user_respostas)
            acertos = 0
            
            if total_respondidas > 0:
                questoes_api = get_questions_from_api_with_cache(s['prova_year'])
                if questoes_api:
                    for q_api in questoes_api:
                        if q_api.get('title') in user_respostas and user_respostas[q_api.get('title')] == q_api.get('correctAlternative'):
                            acertos += 1
            
            timestamp_obj = datetime.strptime(s['timestamp'].split('.')[0], '%Y-%m-%d %H:%M:%S')
            
            historico_data['simulados'].append({
                'id': s['id'], 
                'prova_year': s['prova_year'],
                'timestamp': timestamp_obj.strftime('%d/%m/%Y %H:%M'),
                'duracao_formatada': format_duration(s['duracao_segundos']),
                'acertos': acertos, 
                'total_questoes_respondidas': total_respondidas
            })

        redacoes_db = conn.execute(
            'SELECT id, tema, timestamp FROM redacoes WHERE user_email = ? ORDER BY timestamp DESC', 
            (user_email,)
        ).fetchall()
        
        for r in redacoes_db:
            timestamp_obj = datetime.strptime(r['timestamp'].split('.')[0], '%Y-%m-%d %H:%M:%S')
            historico_data['redacoes'].append({
                'id': r['id'], 
                'tema': r['tema'],
                'timestamp': timestamp_obj.strftime('%d/%m/%Y')
            })
            
    finally:
        if conn: conn.close()
            
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

    # 1. Verifica se o simulado pertence ao usuário logado
    simulado = conn.execute(
        'SELECT * FROM simulados WHERE id = ? AND user_email = ?',
        (simulado_id, user_email)
    ).fetchone()

    if not simulado:
        return jsonify({'error': 'Simulado não encontrado ou não pertence a este usuário.'}), 404

    # 2. Pega as respostas do usuário para este simulado
    respostas_db = conn.execute(
        'SELECT question_unique_id, user_answer FROM respostas_simulado WHERE simulado_id = ?',
        (simulado_id,)
    ).fetchall()
    user_respostas = {r['question_unique_id']: r['user_answer'] for r in respostas_db}
    
    # 3. Usa a função de cache para buscar o gabarito completo da prova na API externa
    prova_year = simulado['prova_year']
    todas_questoes_da_prova = get_questions_from_api_with_cache(prova_year)

    if not todas_questoes_da_prova:
        return jsonify({'error': f'Não foi possível obter o gabarito para a prova de {prova_year}.'}), 500

    # 4. Compara as respostas do usuário com o gabarito
    acertos_totais = 0
    respostas_detalhadas = []

    # Itera sobre a lista de questões que o usuário respondeu
    for q_unique_id, user_answer in user_respostas.items():
        # Encontra a questão correspondente na lista completa da API
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

    # 5. Retorna todos os dados para o front-end
    return jsonify({
        'prova_year': simulado['prova_year'],
        'timestamp': datetime.strptime(simulado['timestamp'].split('.')[0], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M'),
        'duracao_segundos': simulado['duracao_segundos'],
        'acertos_totais': acertos_totais,
        'total_questoes': total_questoes_respondidas,
        'porcentagem_total': round(porcentagem_total, 2),
        'respostas_detalhadas': sorted(respostas_detalhadas, key=lambda x: x['question_number'])
    })

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

    conn = None
    try:
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO redacoes (user_email, tema, texto_redacao) VALUES (?, ?, ?)',
            (user_email, tema, texto_redacao)
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Redação salva com sucesso!'})
    except Exception as e:
        app.logger.error(f"Erro ao salvar redação: {e}")
        return jsonify({'error': 'Ocorreu um erro ao salvar a redação.'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/redacao/<int:redacao_id>')
@login_required
def ver_redacao(redacao_id):
    conn = get_db_connection()
    redacao_db = conn.execute(
        'SELECT * FROM redacoes WHERE id = ? AND user_email = ?',
        (redacao_id, session['user']['email'])
    ).fetchone()
    conn.close()

    if not redacao_db:
        flash('Redação não encontrada ou não pertence a este usuário.', 'danger')
        return redirect(url_for('historico'))
    
    redacao = dict(redacao_db)
    timestamp_obj = datetime.strptime(redacao['timestamp'].split('.')[0], '%Y-%m-%d %H:%M:%S')
    redacao['timestamp_formatado'] = timestamp_obj.strftime('%d/%m/%Y às %H:%M')
    
    return render_template('ver_redacao.html', user=session.get('user'), redacao=redacao)

@app.route('/api/corrigir_redacao/<int:redacao_id>', methods=['POST'])
@login_required
def corrigir_redacao(redacao_id):
    conn = get_db_connection()
    redacao = conn.execute(
        'SELECT * FROM redacoes WHERE id = ? AND user_email = ?',
        (redacao_id, session['user']['email'])
    ).fetchone()

    if not redacao:
        conn.close()
        return jsonify({'error': 'Redação não encontrada.'}), 404

    if redacao['feedback']:
        conn.close()
        return jsonify({
            'nota_total': redacao['nota_total'],
            'notas': [redacao['nota_c1'], redacao['nota_c2'], redacao['nota_c3'], redacao['nota_c4'], redacao['nota_c5']],
            'feedback': redacao['feedback']
        })

    texto_redacao = redacao['texto_redacao']

    prompt = f"""
    Aja como um corretor experiente do ENEM. Avalie a seguinte redação com base nas 5 competências do ENEM.
    Para cada competência, atribua uma nota de 0 a 200, em múltiplos de 40.
    A nota total deve ser a soma das 5 competências.
    Forneça um feedback geral construtivo sobre o texto, destacando pontos fortes e áreas para melhoria.
    O formato da sua resposta DEVE ser um objeto JSON válido, sem nenhum texto antes ou depois, com a seguinte estrutura:
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

    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        
        clean_response = response.text.replace('```json', '').replace('```', '').strip()
        correcao = json.loads(clean_response)

        conn.execute(
            '''UPDATE redacoes SET 
            nota_c1 = ?, nota_c2 = ?, nota_c3 = ?, nota_c4 = ?, nota_c5 = ?, nota_total = ?, feedback = ?
            WHERE id = ?''',
            (correcao['nota_c1'], correcao['nota_c2'], correcao['nota_c3'], correcao['nota_c4'], correcao['nota_c5'], correcao['nota_total'], correcao['feedback'], redacao_id)
        )
        conn.commit()
        conn.close()
        
        resposta_final = {
            'nota_total': correcao['nota_total'],
            'notas': [correcao['nota_c1'], correcao['nota_c2'], correcao['nota_c3'], correcao['nota_c4'], correcao['nota_c5']],
            'feedback': correcao['feedback']
        }
        return jsonify(resposta_final)

    except Exception as e:
        conn.close()
        app.logger.error(f"Erro na API do Gemini ou ao processar a resposta: {e}")
        return jsonify({'error': 'Não foi possível obter a correção da IA no momento.'}), 500

# --- 10. Rotas de Ranking ---
@app.route('/ranking')
def ranking_page():
    return render_template('ranking.html', user=session.get('user'))

@app.route('/api/ranking_geral')
def get_ranking_geral():
    conn = get_db_connection()
    try:
        # Pega todos os dados necessários do banco de uma vez
        simulados = conn.execute('SELECT * FROM simulados').fetchall()
        usuarios = conn.execute('SELECT email, name FROM users').fetchall()
        respostas = conn.execute('SELECT * FROM respostas_simulado').fetchall()

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
                    # CORREÇÃO PRINCIPAL: Usa o título para comparar, como no resto do app
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

# --- 11. Rotas de Administração ---
@app.route('/admin/view_db/<secret_key>')
def view_db(secret_key):
    admin_secret = os.getenv('ADMIN_SECRET_KEY')
    
    if not admin_secret or secret_key != admin_secret:
        return "Acesso não autorizado.", 403

    try:
        conn = get_db_connection()
        tables_cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [table['name'] for table in tables_cursor.fetchall()]
        
        db_data = {}
        for table_name in tables:
            if table_name != 'sessions':
                data_cursor = conn.execute(f"SELECT * FROM {table_name}")
                db_data[table_name] = data_cursor.fetchall()
        
        conn.close()
        return render_template('admin_view.html', db_data=db_data)
    except Exception as e:
        return f"Ocorreu um erro ao acessar o banco de dados: {e}"

# --- 12. Execução da Aplicação ---
if __name__ == '__main__':
    app.run(debug=True)