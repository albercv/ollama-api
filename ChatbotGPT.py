import logging
import subprocess
from quart import Quart, request, jsonify, session
from flask_session import Session
import os
import asyncio

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurar la aplicación Quart
app = Quart(__name__)
app.config['SECRET_KEY'] = os.urandom(24)  # Generar una clave secreta segura
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True

# Inicializa la sesión
Session(app)

# Función para asegurar que el session_id es una cadena
def ensure_string_session_id(response):
    cookies = response.headers.getlist('Set-Cookie')
    for i, cookie in enumerate(cookies):
        if isinstance(cookie, bytes):
            cookies[i] = cookie.decode('utf-8')
        # Verificar si el valor de la cookie es bytes y decodificarlo
        cookie_parts = cookie.split(';')
        for j, part in enumerate(cookie_parts):
            if '=' in part:
                key, value = part.split('=', 1)
                if isinstance(value, bytes):
                    cookie_parts[j] = f"{key}={value.decode('utf-8')}"
        cookies[i] = ';'.join(cookie_parts)
    response.headers.setlist('Set-Cookie', cookies)

async def run_ollama(prompt):
    logger.info(f"Running ollama with prompt: {prompt}")
    process = await asyncio.create_subprocess_exec(
        "ollama", "run", "llama3.1:8b",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False  # text debe ser False para manejar bytes
    )
    stdout, stderr = await process.communicate(input=prompt.encode('utf-8'))
    logger.info(f"Ollama stdout: {stdout.decode('utf-8')}")
    logger.error(f"Ollama stderr: {stderr.decode('utf-8')}")
    return process.returncode, stdout.decode('utf-8'), stderr.decode('utf-8')

@app.route('/ask', methods=['POST'])
async def ask():
    try:
        data = await request.get_json()
        if 'prompt' not in data:
            logger.warning("No prompt provided in the request.")
            return jsonify({'error': 'No prompt provided'}), 400

        prompt = data['prompt']
        logger.info(f"Received prompt: {prompt}")

        # Obtener el historial de conversaciones de la sesión
        conversation_history = session.get('conversation_history', [])

        # Añadir el nuevo prompt al historial de conversaciones
        conversation_history.append(f"User: {prompt}")

        # Crear el prompt completo con el historial de conversaciones
        full_prompt = "\n".join(conversation_history)
        logger.info(f"Full prompt: {full_prompt}")

        # Ejecutar Ollama de forma asíncrona
        returncode, stdout, stderr = await run_ollama(full_prompt)

        if returncode != 0:
            logger.error(f"Ollama error: {stderr}")
            return jsonify({'error': 'Error running Ollama'}), 500

        response = stdout.strip()
        logger.info(f"Generated response: {response}")

        # Añadir la respuesta del modelo al historial de conversaciones
        conversation_history.append(f"AI: {response}")

        # Guardar el historial de conversaciones en la sesión
        session['conversation_history'] = conversation_history

        resp = jsonify({'response': response})
        ensure_string_session_id(resp)
        return resp, 200
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/reset', methods=['POST'])
async def reset():
    session.pop('conversation_history', None)
    resp = jsonify({'message': 'Conversation history reset'})
    ensure_string_session_id(resp)
    return resp, 200

@app.route('/check_session', methods=['GET'])
async def check_session():
    try:
        # Intentar almacenar un valor en la sesión
        session['test_key'] = 'test_value'
        
        # Intentar recuperar el valor de la sesión
        test_value = session.get('test_key', None)
        logger.info(f"Retrieved test_key from session: {test_value}")

        if test_value == 'test_value':
            return jsonify({'message': 'Session storage is working!'}), 200
        else:
            return jsonify({'error': 'Failed to retrieve the correct value from session'}), 500
    except Exception as e:
        logger.error(f"Error checking session: {e}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
async def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
async def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except Exception as e:
        logger.error(f"Failed to start the application: {e}")
