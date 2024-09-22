# Write Python code to create a web application that enables users to interact with a chatbot using both text and image inputs.
from flask import Flask, request, render_template, Response, session, stream_with_context, redirect, url_for
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
import os
from dotenv import load_dotenv
import logging
import base64
import fitz  # PyMuPDF
from langchain_community.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain.memory import ChatMessageHistory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.chains import LLMChain

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Set a secret key for session management
UPLOAD_FOLDER = 'uploads/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit

# Add a password hash (you should change 'your_password_here' to a secure password)
PASSWORD_HASH = generate_password_hash('Gary2024')

# Create uploads folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize ChatOpenAI
chat_model = ChatOpenAI(
    model_name="gpt-4o",
    temperature=0.7,
    max_tokens=300,
    streaming=True
)

# Create a prompt template
prompt = ChatPromptTemplate.from_messages([
    SystemMessage(content="You are a helpful AI assistant."),
    MessagesPlaceholder(variable_name="history"),
    HumanMessage(content="{input}")
])

# Create a dictionary to store chat histories for each session
chat_histories = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        password = request.form.get('password')
        if check_password_hash(PASSWORD_HASH, password):
            session['authenticated'] = True
            return redirect(url_for('chat_ui'))
        else:
            return render_template('login.html', error="Invalid password")
    return render_template('login.html')

@app.route('/chat_ui')
def chat_ui():
    if not session.get('authenticated'):
        return redirect(url_for('index'))
    return render_template('index.html')

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('index'))

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def parse_pdf(file_path):
    doc = fitz.open(file_path)
    text = ""
    images = []
    for page in doc:
        text += page.get_text()
        for img in page.get_images(full=True):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            image_path = f"{file_path}_image_{xref}.{image_ext}"
            with open(image_path, "wb") as img_file:
                img_file.write(image_bytes)
            images.append(image_path)
    return text, images

@app.route('/chat', methods=['POST'])
def chat():
    user_input = request.form['text_input']
    
    # Process uploaded files
    additional_content = []
    image_contents = []
    if 'image_input' in request.files:
        image = request.files['image_input']
        if image.filename != '':
            filename = secure_filename(image.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(image_path)
            image_content = encode_image(image_path)
            image_contents.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_content}"}})
            additional_content.append(f"[Image uploaded: {filename}]")

    if 'pdf_input' in request.files:
        pdf = request.files['pdf_input']
        if pdf.filename != '':
            filename = secure_filename(pdf.filename)
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            pdf.save(pdf_path)
            pdf_text, pdf_images = parse_pdf(pdf_path)
            additional_content.append(f"[PDF content: {pdf_text[:500]}...]")
            for img_path in pdf_images:
                img_content = encode_image(img_path)
                image_contents.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_content}"}})

    # Combine user input with additional content
    full_input = f"{user_input}\n" + "\n".join(additional_content)

    # Get or create session ID
    session_id = session.get('session_id', os.urandom(16).hex())
    session['session_id'] = session_id

    # Get or create chat history for this session
    if session_id not in chat_histories:
        chat_histories[session_id] = ChatMessageHistory()

    # Add the user's message to the history
    chat_histories[session_id].add_user_message(full_input)

    def generate_response():
        try:
            messages = [
                SystemMessage(content="You are a helpful AI assistant. Format your responses using markdown for better readability."),
                *chat_histories[session_id].messages[:-1]  # Exclude the last message
            ]

            # Prepare the content for the last user message
            last_message_content = [{"type": "text", "text": full_input}]
            last_message_content.extend(image_contents)

            # Add the last user message with both text and images
            messages.append(HumanMessage(content=last_message_content))

            for chunk in chat_model.stream(messages):
                yield chunk.content
        
            # Add the AI's response to the history
            chat_histories[session_id].add_ai_message(chunk.content)
        except Exception as e:
            yield f"Error communicating with OpenAI API: {str(e)}"

    return Response(stream_with_context(generate_response()), mimetype='text/plain')

if __name__ == '__main__':
    app.run(debug=True)






















