# app.py
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_dance.contrib.google import make_google_blueprint, google
import requests
import os
from dotenv import load_dotenv
import sqlite3
import json
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# Configuração da API ENEM
ENEM_API_KEY = os.getenv('API_ENEM_KEY')
ENEM_API_BASE_URL = 'https://api.enem.dev/v1'


# Configuração do banco de dados
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Criar tabelas de usuários, simulados e respostas_simulado
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
        conn.commit()
        conn.close()

init_db()

# Configuração do OAuth com Google
google_bp = make_google_blueprint(
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    scope=["profile", "email"],
    redirect_to="google.authorized"
)
app.register_blueprint(google_bp, url_prefix="/login")

@app.route("/")
def index():
    user = session.get('user')
    return render_template('index.html', user=user)

@app.route("/login/google/authorized")
def authorized():
    if not google.authorized:
        flash("Autorização do Google falhou.")
        return redirect(url_for("google.login"))
    try:
        resp = google.get("/oauth2/v2/userinfo")
        resp.raise_for_status()
        user_info = resp.json()

        email = user_info['email']
        name = user_info.get('name', email.split('@')[0])

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        
        if not user:
            conn.execute('INSERT INTO users (email, name, password) VALUES (?, ?, ?)',
                        (email, name, 'OAUTH_GOOGLE_PLACEHOLDER'))
            conn.commit()
        conn.close()

        session['user'] = {
            'email': email,
            'name': name
        }
        flash("Login com Google realizado com sucesso!")
        return redirect(url_for("index"))
    except requests.exceptions.RequestException as e:
        flash(f"Erro ao obter informações do Google: {e}")
        return redirect(url_for("login"))
    except Exception as e:
        flash(f"Erro inesperado no login com Google: {e}")
        return redirect(url_for("login"))

@app.route('/login/email', methods=['POST'])
def login_email():
    email = request.form['email']
    password = request.form['password']
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()
    
    if user and check_password_hash(user['password'], password):
        session['user'] = {
            'email': user['email'],
            'name': user['name'] or user['email'].split('@')[0]
        }
        flash('Login realizado com sucesso!')
        return redirect(url_for('index'))
    else:
        flash('Email ou senha incorretos.')
        return redirect(url_for('login'))

@app.route('/register', methods=['POST'])
def register():
    email = request.form['email']
    password = request.form['password']
    name = request.form.get('name', '')

    hashed_password = generate_password_hash(password)
    
    try:
        conn = get_db_connection()
        conn.execute('INSERT INTO users (email, password, name) VALUES (?, ?, ?)',
                    (email, hashed_password, name))
        conn.commit()
        conn.close()
        
        session['user'] = {
            'email': email,
            'name': name or email.split('@')[0]
        }
        flash('Cadastro realizado com sucesso!')
        return redirect(url_for('index'))
    except sqlite3.IntegrityError:
        flash('Email já cadastrado.')
        return redirect(url_for('login'))

@app.route("/login")
def login():
    if 'user' in session:
        return redirect(url_for('index'))
    messages = session.pop('_flashes', [])
    return render_template('login.html', messages=messages)

@app.route("/logout")
def logout():
    session.pop('user', None)
    flash('Você foi desconectado.')
    return redirect(url_for('index'))

@app.route('/exame')
def exame():
    if 'user' not in session:
        flash('Você precisa estar logado para acessar os simulados.')
        return redirect(url_for('login'))
    user = session.get('user')
    return render_template('exame.html', user=user)

@app.route('/api/provas')
def get_provas():
    try:
        response = requests.get(f'{ENEM_API_BASE_URL}/exams')
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.RequestException as req_e:
        print(f"Erro na requisição para API ENEM (provas): {req_e}")
        return jsonify({'error': f"Erro de rede ou API externa: {req_e}"}), 500
    except ValueError as val_e:
        print(f"Erro ao decodificar JSON da API ENEM (provas): {val_e}")
        return jsonify({'error': f"Resposta inválida da API externa: {val_e}"}), 500
    except Exception as e:
        print(f"Erro inesperado em get_provas: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/provas/<year>/questoes')
def get_questoes(year):
    try:
        response = requests.get(f'{ENEM_API_BASE_URL}/exams/{year}/questions')
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.RequestException as req_e:
        print(f"Erro na requisição para API ENEM (questoes): {req_e}")
        return jsonify({'error': f"Erro de rede ou API externa: {req_e}"}), 500
    except ValueError as val_e:
        print(f"Erro ao decodificar JSON da API ENEM (questoes): {val_e}")
        return jsonify({'error': f"Resposta inválida da API externa: {val_e}"}), 500
    except Exception as e:
        print(f"Erro inesperado em get_questoes: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/submit', methods=['POST'])
def submit_answers():
    if 'user' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

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
        
        flash('Respostas enviadas com sucesso! Veja seu resultado.')
        return jsonify({'success': True, 'redirect_url': url_for('resultado_detalhe', simulado_id=simulado_id)})
    except Exception as e:
        print(f"Erro ao salvar respostas: {e}")
        flash(f'Erro ao salvar respostas: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/historico')
def historico():
    if 'user' not in session:
        flash('Você precisa estar logado para acessar seu histórico.')
        return redirect(url_for('login'))
    user = session.get('user')
    return render_template('historico.html', user=user)

# API para obter o histórico de simulados do usuário COM PONTUAÇÃO
@app.route('/api/historico')
def get_historico():
    if 'user' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    user_email = session['user']['email']
    conn = get_db_connection()
    simulados_feitos = conn.execute(
        'SELECT id, prova_year, duracao_segundos, timestamp FROM simulados WHERE user_email = ? ORDER BY timestamp DESC',
        (user_email,)
    ).fetchall()
    conn.close()

    historico_data = []
    for s in simulados_feitos:
        # Calcular acertos para cada simulado
        simulado_id = s['id']
        prova_year = s['prova_year']
        
        conn_inner = get_db_connection() # Nova conexão para evitar conflitos
        user_respostas_db = conn_inner.execute(
            'SELECT question_unique_id, user_answer FROM respostas_simulado WHERE simulado_id = ?',
            (simulado_id,)
        ).fetchall()
        conn_inner.close()

        user_respostas = {r['question_unique_id']: r['user_answer'] for r in user_respostas_db}
        
        acertos_totais = 0
        total_questoes_respondidas = len(user_respostas)

        if total_questoes_respondidas > 0:
            try:
                # Buscar o gabarito para este ano da prova
                response_api = requests.get(f'{ENEM_API_BASE_URL}/exams/{prova_year}/questions')
                response_api.raise_for_status()
                questoes_api = response_api.json().get('questions', [])

                for q_api in questoes_api:
                    q_unique_id = q_api.get('title') # Ou q_api.get('id') se usado no frontend
                    if not q_unique_id:
                         q_unique_id = f"questao-{q_api.get('year', '')}-{q_api.get('index', '')}"

                    if q_unique_id in user_respostas:
                        user_resp = user_respostas[q_unique_id]
                        gabarito_resp = q_api.get('correctAlternative') # CORREÇÃO: Usar 'correctAlternative'

                        if user_resp == gabarito_resp and user_resp is not None:
                            acertos_totais += 1
            except requests.exceptions.RequestException as e:
                print(f"Erro ao buscar gabarito para simulado {simulado_id} no histórico: {e}")
                acertos_totais = "Erro" # Indicar erro se não conseguir o gabarito
                total_questoes_respondidas = "Erro"
            except Exception as e:
                print(f"Erro inesperado ao processar simulado {simulado_id} no histórico: {e}")
                acertos_totais = "Erro"
                total_questoes_respondidas = "Erro"
        else:
            acertos_totais = 0
            total_questoes_respondidas = 0

        # Formata a duração para ser mais legível
        duracao_formatada = ""
        if s['duracao_segundos'] is not None:
            horas = s['duracao_segundos'] // 3600
            minutos = (s['duracao_segundos'] % 3600) // 60
            segundos = s['duracao_segundos'] % 60
            if horas > 0:
                duracao_formatada += f"{horas}h "
            if minutos > 0:
                duracao_formatada += f"{minutos}m "
            if segundos > 0 or (horas == 0 and minutos == 0):
                duracao_formatada += f"{segundos}s"
            duracao_formatada = duracao_formatada.strip()

        historico_data.append({
            'id': s['id'],
            'prova_year': s['prova_year'],
            'timestamp': datetime.strptime(s['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M'),
            'duracao_formatada': duracao_formatada,
            'acertos': acertos_totais, # Adicionado
            'total_questoes_respondidas': total_questoes_respondidas # Adicionado
        })
    
    return jsonify(historico_data)


# Rota para a página de detalhes de um simulado específico
@app.route('/resultado/<int:simulado_id>')
def resultado_detalhe(simulado_id):
    if 'user' not in session:
        flash('Você precisa estar logado para ver os resultados.')
        return redirect(url_for('login'))
    user = session.get('user')
    return render_template('resultado.html', user=user, simulado_id=simulado_id)


# API para obter o resultado detalhado de um simulado específico
@app.route('/api/resultado/<int:simulado_id>')
def get_resultado_detalhado(simulado_id):
    if 'user' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    user_email = session['user']['email']
    conn = get_db_connection()

    simulado = conn.execute(
        'SELECT id, user_email, prova_year, duracao_segundos, timestamp FROM simulados WHERE id = ? AND user_email = ?',
        (simulado_id, user_email)
    ).fetchone()

    if not simulado:
        conn.close()
        return jsonify({'error': 'Simulado não encontrado ou não pertence a este usuário.'}), 404

    prova_year = simulado['prova_year']
    
    user_respostas_db = conn.execute(
        'SELECT question_unique_id, user_answer FROM respostas_simulado WHERE simulado_id = ?',
        (simulado_id,)
    ).fetchall()
    conn.close()

    user_respostas = {r['question_unique_id']: r['user_answer'] for r in user_respostas_db}

    try:
        response = requests.get(f'{ENEM_API_BASE_URL}/exams/{prova_year}/questions')
        response.raise_for_status()
        questoes_api = response.json()
    except requests.exceptions.RequestException as req_e:
        print(f"Erro ao buscar questões/gabarito da API ENEM: {req_e}")
        return jsonify({'error': f"Não foi possível obter gabarito da prova {prova_year}: {req_e}"}), 500
    except Exception as e:
        print(f"Erro inesperado ao obter gabarito: {e}")
        return jsonify({'error': str(e)}), 500

    todas_questoes_da_prova = questoes_api.get('questions', [])
    
    acertos_totais = 0
    total_questoes_para_calculo = len(user_respostas) # Usa o número de questões que o usuário respondeu

    respostas_detalhadas = []
    acertos_por_disciplina = {}
    total_por_disciplina = {}

    for q in todas_questoes_da_prova:
        q_unique_id = q.get('title')
        if not q_unique_id:
            q_unique_id = f"questao-{q.get('year', '')}-{q.get('index', '')}"
        
        # Só processa se a questão foi respondida pelo usuário
        if q_unique_id in user_respostas:
            user_resp = user_respostas.get(q_unique_id)
            # CORREÇÃO AQUI: Usar 'correctAlternative' da API para o gabarito
            gabarito_resp = q.get('correctAlternative') 

            acertou = (user_resp == gabarito_resp and user_resp is not None)

            if acertou:
                acertos_totais += 1

            disciplina = q.get('discipline', 'Outros')
            acertos_por_disciplina[disciplina] = acertos_por_disciplina.get(disciplina, 0) + (1 if acertou else 0)
            total_por_disciplina[disciplina] = total_por_disciplina.get(disciplina, 0) + 1

            respostas_detalhadas.append({
                'question_number': q.get('index'),
                'question_title': q.get('title'),
                'discipline': disciplina,
                'user_answer': user_resp,
                'correct_answer': gabarito_resp,
                'alternatives': q.get('alternatives'),
                'question_context': q.get('context'),
                'alternatives_introduction': q.get('alternativesIntroduction'),
                'acertou': acertou
            })
    
    porcentagem_total = (acertos_totais / total_questoes_para_calculo) * 100 if total_questoes_para_calculo > 0 else 0

    porcentagem_por_disciplina = {}
    for disc, total in total_por_disciplina.items():
        acertos_disc = acertos_por_disciplina.get(disc, 0)
        porcentagem_por_disciplina[disc] = (acertos_disc / total) * 100 if total > 0 else 0

    return jsonify({
        'simulado_id': simulado['id'],
        'prova_year': simulado['prova_year'],
        'timestamp': datetime.strptime(simulado['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M'),
        'duracao_segundos': simulado['duracao_segundos'],
        'acertos_totais': acertos_totais,
        'total_questoes': total_questoes_para_calculo,
        'porcentagem_total': round(porcentagem_total, 2),
        'acertos_por_disciplina': acertos_por_disciplina,
        'total_por_disciplina': total_por_disciplina,
        'porcentagem_por_disciplina': {k: round(v, 2) for k, v in porcentagem_por_disciplina.items()},
        'respostas_detalhadas': respostas_detalhadas
    })

# Adicione esta nova rota no app.py (antes do if __name__ == '__main__')
@app.route('/api/ranking_geral')
def get_ranking_geral():
    try:
        conn = get_db_connection()

        # Pega todos os simulados
        simulados = conn.execute('SELECT * FROM simulados').fetchall()
        usuarios = conn.execute('SELECT email, name FROM users').fetchall()
        conn.close()

        # Indexa os usuários por email
        usuarios_dict = {u['email']: u['name'] for u in usuarios}

        ranking_temp = {}  # Agrupar por email

        for s in simulados:
            user_email = s['user_email']
            prova_year = s['prova_year']
            duracao = s['duracao_segundos'] or 0

            # Coletar respostas
            conn = get_db_connection()
            respostas = conn.execute(
                'SELECT question_unique_id, user_answer FROM respostas_simulado WHERE simulado_id = ?',
                (s['id'],)
            ).fetchall()
            conn.close()

            if not respostas:
                continue

            user_respostas = {r['question_unique_id']: r['user_answer'] for r in respostas}

            # Chamar API para obter gabarito
            try:
                r = requests.get(f'{ENEM_API_BASE_URL}/exams/{prova_year}/questions')
                r.raise_for_status()
                questoes = r.json().get('questions', [])
            except:
                continue  # Ignora se API falhar

            acertos = 0
            total = 0

            for q in questoes:
                qid = q.get('title') or f"questao-{q.get('year')}-{q.get('index')}"
                if qid in user_respostas:
                    total += 1
                    if user_respostas[qid] == q.get('correctAlternative'):
                        acertos += 1

            if total == 0:
                continue

            if user_email not in ranking_temp:
                ranking_temp[user_email] = {
                    'name': usuarios_dict.get(user_email, user_email),
                    'acertos_totais': 0,
                    'total_questoes': 0,
                    'duracoes': []
                }

            ranking_temp[user_email]['acertos_totais'] += acertos
            ranking_temp[user_email]['total_questoes'] += total
            ranking_temp[user_email]['duracoes'].append(duracao)

        # Agora gerar a lista
        ranking = []
        for user_email, dados in ranking_temp.items():
            total_acertos = dados['acertos_totais']
            total_q = dados['total_questoes']
            media_duracao = sum(dados['duracoes']) // len(dados['duracoes']) if dados['duracoes'] else 0

            horas = media_duracao // 3600
            minutos = (media_duracao % 3600) // 60
            segundos = media_duracao % 60
            duracao_formatada = f"{horas:02}:{minutos:02}:{segundos:02}"

            ranking.append({
                'name': dados['name'],
                'porcentagem': round((total_acertos / total_q) * 100, 2),
                'duracao_formatada': duracao_formatada,
                'acertos': total_acertos,
                'total_questoes': total_q
            })

        # Ordenar por desempenho
        ranking.sort(key=lambda x: (-x['porcentagem'], x['duracao_formatada']))

        return jsonify(ranking[:50])  # top 50

    except Exception as e:
        print(f"Erro ao gerar ranking: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/ranking')
def ranking_page():
    user = session.get('user')
    return render_template('ranking.html', user=user)

if __name__ == '__main__':
    app.run(debug=True)