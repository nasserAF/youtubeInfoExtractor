from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled
import re
import os
from datetime import datetime
from googleapiclient.discovery import build
from dotenv import load_dotenv
from firebase_config import db, SERVER_TIMESTAMP, auth_client
from functools import wraps
import jwt

# تحميل المتغيرات البيئية من ملف .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key')

def authenticate_firebase_user(email, password):
    try:
        # Sign in with Firebase
        auth_response = auth_client.sign_in_with_email_and_password(email, password)
        
        # Get fresh ID token
        user = auth_client.refresh(auth_response['refreshToken'])
        
        # Get user info
        user_info = auth_client.get_account_info(user['idToken'])
        
        # Store token in session
        session['id_token'] = user['idToken']
        session['refresh_token'] = user['refreshToken']
        
        return user_info['users'][0]
    except Exception as e:
        print(f"Firebase authentication error: {str(e)}")
        return None

# تكوين Firebase
app.config.update({
    'FIREBASE_API_KEY': os.getenv('FIREBASE_API_KEY'),
    'FIREBASE_AUTH_DOMAIN': os.getenv('FIREBASE_AUTH_DOMAIN'),
    'FIREBASE_PROJECT_ID': os.getenv('FIREBASE_PROJECT_ID'),
    'FIREBASE_STORAGE_BUCKET': os.getenv('FIREBASE_STORAGE_BUCKET'),
    'FIREBASE_MESSAGING_SENDER_ID': os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
    'FIREBASE_APP_ID': os.getenv('FIREBASE_APP_ID')
})

# الحصول على مفتاح API من ملف .env
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

# Decorator للتحقق من تسجيل الدخول
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        print("Session contents:", session)  # للتحقق من محتويات الجلسة
        
        if 'user_id' not in session:
            print("No user_id in session")
            return jsonify({
                'success': False,
                'require_auth': True,
                'message': 'يرجى تسجيل الدخول للوصول إلى هذه الميزة'
            }), 401
            
        try:
            # التحقق من صحة الجلسة
            id_token = session.get('id_token')
            if id_token:
                try:
                    # التحقق من صحة التوكن
                    auth_client.verify_id_token(id_token)
                except Exception as e:
                    print(f"Token verification failed: {str(e)}")
                    # محاولة تحديث التوكن
                    refresh_token = session.get('refresh_token')
                    if refresh_token:
                        try:
                            user = auth_client.refresh(refresh_token)
                            session['id_token'] = user['idToken']
                        except Exception as e:
                            print(f"Token refresh failed: {str(e)}")
                            session.clear()
                            return jsonify({
                                'success': False,
                                'require_auth': True,
                                'message': 'انتهت صلاحية الجلسة. يرجى تسجيل الدخول مرة أخرى'
                            }), 401
            
            return f(*args, **kwargs)
        except Exception as e:
            print(f"Login verification error: {str(e)}")
            session.clear()
            return jsonify({
                'success': False,
                'require_auth': True,
                'message': 'حدث خطأ في التحقق من تسجيل الدخول'
            }), 401
            
    return decorated_function

@app.route('/auth/google', methods=['POST'])
def google_auth():
    try:
        print("Received Google auth request")
        # استلام توكن المصادقة من Google
        id_token = request.json.get('idToken')
        if not id_token:
            print("No ID token provided")
            return jsonify({'error': 'لم يتم توفير توكن المصادقة'}), 400

        print("Verifying ID token")
        # التحقق من صحة التوكن
        decoded_token = auth_client.verify_id_token(id_token)
        print("Token verified successfully:", decoded_token)
        
        # حفظ معلومات المستخدم في الجلسة
        session['user_id'] = decoded_token['uid']
        session['email'] = decoded_token.get('email')
        session['name'] = decoded_token.get('name')
        session['id_token'] = id_token
        
        print("Session updated:", session)
        
        # إضافة المستخدم إلى Firestore إذا لم يكن موجوداً
        try:
            user_ref = db.collection('users').document(decoded_token['uid'])
            if not user_ref.get().exists:
                user_data = {
                    'name': decoded_token.get('name'),
                    'email': decoded_token.get('email'),
                    'created_at': SERVER_TIMESTAMP
                }
                user_ref.set(user_data)
                print("New user created in Firestore:", user_data)
        except Exception as e:
            print("Error saving user to Firestore:", str(e))
            # نستمر حتى لو فشل حفظ البيانات في Firestore
            pass

        return jsonify({
            'success': True,
            'message': 'تم تسجيل الدخول بنجاح',
            'user': {
                'name': session.get('name'),
                'email': session.get('email')
            }
        })
    except Exception as e:
        print("Google auth error:", str(e))
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = authenticate_firebase_user(email, password)
        if user:
            # Store user info in session
            session['user_id'] = user['localId']
            session['email'] = user['email']
            session['name'] = user.get('displayName')
            
            flash('تم تسجيل الدخول بنجاح!', 'success')
            return redirect(url_for('extract'))
        else:
            flash('خطأ في البريد الإلكتروني أو كلمة المرور', 'error')
            return render_template('login.html', error='خطأ في البريد الإلكتروني أو كلمة المرور')
    
    # Pass Firebase config to template
    firebase_config = {
        'apiKey': app.config['FIREBASE_API_KEY'],
        'authDomain': app.config['FIREBASE_AUTH_DOMAIN'],
        'projectId': app.config['FIREBASE_PROJECT_ID'],
        'storageBucket': app.config['FIREBASE_STORAGE_BUCKET'],
        'messagingSenderId': app.config['FIREBASE_MESSAGING_SENDER_ID'],
        'appId': app.config['FIREBASE_APP_ID']
    }
    return render_template('login.html', firebase_config=firebase_config)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            name = request.form['name']
            email = request.form['email']
            password = request.form['password']
            
            # Create user in Firebase
            user = auth_client.create_user(
                email=email,
                password=password,
                display_name=name
            )
            
            # Store additional user data in Firestore if needed
            db.collection('users').document(user.uid).set({
                'name': name,
                'email': email,
                'created_at': SERVER_TIMESTAMP
            })
            
            flash('تم إنشاء الحساب بنجاح! يمكنك الآن تسجيل الدخول.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            flash(str(e), 'error')
            return render_template('register.html', error=str(e))
            
    return render_template('register.html')

@app.route('/extract')
@login_required
def extract():
    return render_template('extract.html')

@app.route('/captions')
@login_required
def captions():
    return render_template('captions.html')

@app.route('/get-cc', methods=['POST'])
@login_required
def get_cc():
    try:
        youtube_url = request.form['youtube_url']
        cc_type = request.form['cc_type']  # 'manual' or 'auto'
        video_id = extract_video_id(youtube_url)
        
        if not video_id:
            return jsonify({'error': 'رابط يوتيوب غير صالح'})

        # Check if video exists in Firestore only for automatic translations
        videos_ref = db.collection('YT-CC')
        if cc_type == 'auto':
            query = videos_ref.where('video_id', '==', video_id).where('cc_type', '==', cc_type).limit(1).get()
            if len(query) > 0:
                return jsonify({'error': 'هذا الفيديو موجود مسبقاً في قاعدة البيانات'})

        try:
            # Get all available transcripts
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            if cc_type == 'manual':
                try:
                    # Try to get manual transcript in Arabic or English
                    transcript = transcript_list.find_manually_created_transcript(['ar', 'en'])
                    # Check if manual transcript video exists in Firestore after confirming transcript exists
                    query = videos_ref.where('video_id', '==', video_id).where('cc_type', '==', cc_type).limit(1).get()
                    if len(query) > 0:
                        return jsonify({'error': 'هذا الفيديو موجود مسبقاً في قاعدة البيانات'})
                except:
                    return jsonify({'error': 'لا توجد ترجمة يدوية متاحة لهذا الفيديو'})
            else:  # auto
                try:
                    # Try to get auto-generated transcript in Arabic or English
                    transcript = transcript_list.find_generated_transcript(['ar', 'en'])
                except:
                    return jsonify({'error': 'لا توجد ترجمة تلقائية متاحة لهذا الفيديو'})

            # Get the transcript
            transcript_data = transcript.fetch()
            
            # Format the transcript
            formatted_transcript = ""
            for entry in transcript_data:
                time = entry['start']
                minutes = int(time // 60)
                seconds = int(time % 60)
                text = entry['text']
                formatted_transcript += f"[{minutes:02d}:{seconds:02d}] {text}\n"
            
            return jsonify({
                'success': True,
                'cc_text': formatted_transcript if formatted_transcript else "لا يوجد محتوى للترجمة",
                'cc_type': 'يدوية' if cc_type == 'manual' else 'تلقائية'
            })
            
        except NoTranscriptFound:
            error_msg = 'لا توجد ترجمة يدوية متاحة لهذا الفيديو' if cc_type == 'manual' else 'لا توجد ترجمة تلقائية متاحة لهذا الفيديو'
            return jsonify({'error': error_msg})
            
    except Exception as e:
        error_msg = str(e)
        if "Subtitles are disabled" in error_msg:
            return jsonify({'error': 'الترجمات معطلة لهذا الفيديو'})
        return jsonify({'error': 'حدث خطأ أثناء جلب الترجمة'})

@app.route('/video_info/<video_id>')
@login_required
def video_info(video_id):
    try:
        # الحصول على معلومات الفيديو
        video_response = youtube.videos().list(
            part='snippet,statistics,contentDetails',
            id=video_id
        ).execute()

        if not video_response['items']:
            return jsonify({'error': 'فيديو غير موجود'})

        video = video_response['items'][0]
        snippet = video['snippet']
        statistics = video['statistics']
        
        # تحويل مدة الفيديو من صيغة ISO 8601 إلى صيغة مقروءة
        duration = video['contentDetails']['duration']
        duration = duration.replace('PT', '').replace('H', ':').replace('M', ':').replace('S', '')
        duration_parts = duration.split(':')
        if len(duration_parts) == 3:
            hours, minutes, seconds = duration_parts
            formatted_duration = f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}"
        elif len(duration_parts) == 2:
            minutes, seconds = duration_parts
            formatted_duration = f"{int(minutes)}:{int(seconds):02d}"
        else:
            seconds = duration_parts[0]
            formatted_duration = f"0:{int(seconds):02d}"

        # تنسيق عدد المشاهدات
        views = int(statistics.get('viewCount', 0))
        if views >= 1000000:
            formatted_views = f"{views/1000000:.1f}M"
        elif views >= 1000:
            formatted_views = f"{views/1000:.1f}K"
        else:
            formatted_views = str(views)

        return jsonify({
            'title': snippet['title'],
            'channel_title': snippet['channelTitle'],
            'channel_url': f"https://www.youtube.com/channel/{snippet['channelId']}",
            'views': formatted_views,
            'duration': formatted_duration,
            'thumbnail_url': snippet['thumbnails']['medium']['url'],
            'thumbnail_max_res': snippet['thumbnails'].get('maxres', snippet['thumbnails']['high'])['url']
        })

    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/save-cc', methods=['POST'])
@login_required
def save_cc():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'لم يتم استلام البيانات'})
            
        video_id = data.get('video_id')
        if not video_id:
            return jsonify({'error': 'معرف الفيديو غير موجود'})
            
        video_info = data.get('video_info')
        if not video_info:
            return jsonify({'error': 'معلومات الفيديو غير موجودة'})
            
        cc_data = data.get('cc_data')
        if not cc_data:
            return jsonify({'error': 'بيانات الترجمة غير موجودة'})
            
        cc_type = data.get('cc_type')
        if not cc_type:
            return jsonify({'error': 'نوع الترجمة غير محدد'})
        
        # إضافة معرف المستخدم للبيانات
        user_id = session.get('user_id')
        
        # Create a new document in the YT-CC collection
        doc_ref = db.collection('YT-CC').document()
        doc_ref.set({
            'video_id': video_id,
            'video_info': video_info,
            'cc_data': cc_data,
            'cc_type': cc_type,
            'user_id': user_id,  # إضافة معرف المستخدم
            'timestamp': SERVER_TIMESTAMP
        })
        
        return jsonify({'success': True, 'message': 'تم حفظ البيانات بنجاح'})
    except Exception as e:
        print(f"Error saving to Firestore: {str(e)}")
        return jsonify({'error': f'خطأ في حفظ البيانات: {str(e)}'})

@app.route('/get-captions')
@login_required
def get_captions():
    # قراءة الترجمات من Firestore للمستخدم الحالي فقط
    user_id = session.get('user_id')
    captions_ref = db.collection('YT-CC').where('user_id', '==', user_id)
    docs = captions_ref.stream()
    
    captions = []
    for doc in docs:
        caption_data = doc.to_dict()
        caption_data['id'] = doc.id
        captions.append(caption_data)
    
    return jsonify(captions)

@app.route('/delete-caption/<video_id>', methods=['DELETE'])
@login_required
def delete_caption(video_id):
    try:
        db.collection('YT-CC').document(video_id).delete()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def extract_video_id(youtube_url):
    """
    Extract video ID from various YouTube URL formats.
    Returns None if the URL is invalid.
    """
    if not youtube_url:
        return None

    # Regular expressions for different YouTube URL formats
    patterns = [
        r'(?:v=|v/|embed/|youtu\.be/)([^"&?/\s]{11})',  # Standard, shortened and embed URLs
        r'(?:watch\?|v=)([^"&?/\s]{11})',  # Another variation
        r'([^"&?/\s]{11})'  # Just the video ID
    ]

    # Try each pattern
    for pattern in patterns:
        match = re.search(pattern, youtube_url)
        if match:
            return match.group(1)

    return None

if __name__ == '__main__':
    app.run(debug=True)