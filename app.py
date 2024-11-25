import os
import random
import base64
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import io
from passlib.hash import pbkdf2_sha256

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
db = SQLAlchemy(app)

# Определяем модель пользователя
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    birthday = db.Column(db.String(10), nullable=True)
    nickname = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    captcha_code = db.Column(db.String(6), nullable=False)

# Определяем модель сообщения
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.form
        phone_number = data.get('phone_number')
        username = data.get('username')
        password = data.get('password')
        confirm_password = data.get('confirm_password')

        # Проверка на наличие обязательных полей
        if not phone_number or not username or not password or not confirm_password:
            return jsonify({"message": "Все поля обязательны!"}), 400

        if password != confirm_password:
            return jsonify({"message": "Пароли не совпадают!"}), 400

        captcha_code, captcha_image = generate_captcha()

        # Проверяем, существует ли пользователь с таким номером телефона или юзернеймом
        if User.query.filter((User.phone_number == phone_number) | (User.username == username)).first():
            return jsonify({"message": "Пользователь с таким номером телефона или юзернеймом уже зарегистрирован."}), 400

        # Хешируем пароль
        hashed_password = pbkdf2_sha256.hash(password)

        # Сохраняем пользователя
        user = User(phone_number=phone_number, username=username, password=hashed_password, nickname=username, captcha_code=captcha_code)
        db.session.add(user)
        db.session.commit()

        return jsonify({"message": "Регистрация прошла успешно!"})

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.form
        username = data.get('username')
        password = data.get('password')

        user = User.query.filter_by(username=username).first()
        if user and pbkdf2_sha256.verify(password, user.password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('chat'))

        return jsonify({"message": "Неверное имя пользователя или пароль."}), 400

    return render_template('login.html')

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    return render_template('chat.html', username=session['username'])

def generate_captcha():
    captcha_code = str(random.randint(100000, 999999))
    image = Image.new('RGB', (200, 70), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((10, 10), captcha_code, fill=(0, 0, 0), font=font)
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    buf.seek(0)
    captcha_image = base64.b64encode(buf.getvalue()).decode('utf-8')
    return captcha_code, f"data:image/png;base64,{captcha_image}"

@socketio.on('send_message')
def handle_send_message(data):
    username = data['username']
    recipient_username = data['recipient']
    content = data['content']

    recipient = User.query.filter_by(username=recipient_username).first()
    if recipient:
        message = Message(sender_id=session['user_id'], recipient_id=recipient.id, content=content)
        db.session.add(message)
        db.session.commit()
        emit('receive_message', {'username': username, 'message': content}, room=recipient.id)

@socketio.on('personal_message')
def personal_message(data):
    sender_username = data['sender']
    recipient_username = data['recipient']
    content = data['content']

    recipient = User.query.filter_by(username=recipient_username).first()
    if recipient:
        emit('receive_message', {'username': sender_username, 'message': content}, room=recipient.id)

@app.route('/history')
def history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    messages = Message.query.filter((Message.sender_id == session['user_id']) | (Message.recipient_id == session['user_id'])).all()
    return jsonify([{'username': User.query.get(msg.sender_id).username, 'message': msg.content} for msg in messages])

if __name__ == '__main__':
    socketio.run(app)