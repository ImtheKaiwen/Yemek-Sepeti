from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///yemeksepeti.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Upload klasörünü oluştur
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Veritabanı Modelleri
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    profile_image = db.Column(db.String(200))
    address = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    orders = db.relationship('Order', backref='user', lazy=True)
    reviews = db.relationship('Review', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Restaurant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    image = db.Column(db.String(200))
    category = db.Column(db.String(50))
    rating = db.Column(db.Float, default=0.0)
    menu_items = db.relationship('MenuItem', backref='restaurant', lazy=True)

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(200))
    category = db.Column(db.String(50))
    rating = db.Column(db.Float, default=0.0)  # Menü öğesi için ortalama puan
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), nullable=False)
    reviews = db.relationship('Review', backref='menu_item', lazy=True)

    def update_rating(self):
        if self.reviews:
            self.rating = sum(review.rating for review in self.reviews) / len(self.reviews)
        else:
            self.rating = 0.0

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), nullable=False)
    order_time = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')
    total_amount = db.Column(db.Float, default=0.0)
    items = db.relationship('OrderItem', backref='order', lazy=True)
    restaurant = db.relationship('Restaurant', backref='orders', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    menu_item = db.relationship('MenuItem', backref='order_items', lazy=True)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Sepet işlemleri
def get_cart():
    if 'cart' not in session:
        session['cart'] = []
    return session['cart']

def add_to_cart(item_id, quantity):
    cart = get_cart()
    menu_item = MenuItem.query.get(item_id)
    
    if menu_item:
        # Aynı restorandan mı kontrol et
        if cart and cart[0]['restaurant_id'] != menu_item.restaurant_id:
            return False, "Sepetinizde başka bir restorandan ürün var. Önce sepetinizi temizleyin."
        
        # Ürün zaten sepette var mı kontrol et
        for item in cart:
            if item['id'] == item_id:
                item['quantity'] += quantity
                session['cart'] = cart
                return True, "Ürün miktarı güncellendi."
        
        # Yeni ürün ekle
        cart.append({
            'id': item_id,
            'name': menu_item.name,
            'price': menu_item.price,
            'quantity': quantity,
            'restaurant_id': menu_item.restaurant_id
        })
        session['cart'] = cart
        return True, "Ürün sepete eklendi."
    return False, "Ürün bulunamadı."

def remove_from_cart(item_id):
    cart = get_cart()
    cart = [item for item in cart if item['id'] != item_id]
    session['cart'] = cart
    return True, "Ürün sepetten kaldırıldı."

def get_cart_total():
    cart = get_cart()
    return sum(item['price'] * item['quantity'] for item in cart)

# Routes
@app.route('/')
def index():
    restaurants = Restaurant.query.all()
    return render_template('index.html', restaurants=restaurants)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/restaurant/<int:restaurant_id>')
def restaurant_detail(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    price_range = request.args.get('price_range', '')
    
    menu_items = MenuItem.query.filter_by(restaurant_id=restaurant_id)
    
    if query:
        menu_items = menu_items.filter(MenuItem.name.ilike(f'%{query}%'))
    if category:
        menu_items = menu_items.filter(MenuItem.category == category)
    if price_range:
        if price_range == '0-50':
            menu_items = menu_items.filter(MenuItem.price <= 50)
        elif price_range == '50-100':
            menu_items = menu_items.filter(MenuItem.price > 50, MenuItem.price <= 100)
        elif price_range == '100+':
            menu_items = menu_items.filter(MenuItem.price > 100)
    
    menu_items = menu_items.all()
    
    return render_template('restaurant_detail.html', restaurant=restaurant, 
                         menu_items=menu_items, query=query, 
                         category=category, price_range=price_range)

@app.route('/menu_item/<int:item_id>')
def menu_item_detail(item_id):
    menu_item = MenuItem.query.get_or_404(item_id)
    reviews = Review.query.filter_by(menu_item_id=item_id).all()
    return render_template('menu_item_detail.html', menu_item=menu_item, reviews=reviews)

@app.route('/add_to_cart/<int:item_id>', methods=['POST'])
@login_required
def add_to_cart_route(item_id):
    quantity = int(request.form.get('quantity', 1))
    success, message = add_to_cart(item_id, quantity)
    flash(message)
    return redirect(url_for('menu_item_detail', item_id=item_id))

@app.route('/remove_from_cart/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart_route(item_id):
    success, message = remove_from_cart(item_id)
    flash(message)
    return redirect(url_for('cart'))

@app.route('/cart')
@login_required
def cart():
    cart_items = get_cart()
    total = get_cart_total()
    return render_template('cart.html', cart=cart_items, total=total)

@app.route('/place_order', methods=['POST'])
@login_required
def place_order():
    cart_items = get_cart()
    if not cart_items:
        flash('Sepetiniz boş', 'warning')
        return redirect(url_for('cart'))
    
    # Sipariş oluştur
    order = Order(
        user_id=current_user.id,
        restaurant_id=cart_items[0]['restaurant_id'],
        total_amount=get_cart_total()
    )
    db.session.add(order)
    db.session.commit()
    
    # Sipariş öğelerini ekle
    for item in cart_items:
        menu_item = MenuItem.query.get(item['id'])
        if menu_item:
            order_item = OrderItem(
                order_id=order.id,
                menu_item_id=item['id'],
                quantity=item['quantity'],
                price=menu_item.price  # Menü öğesinin güncel fiyatını kullan
            )
            db.session.add(order_item)
    
    db.session.commit()
    
    # Sepeti temizle
    session['cart'] = []
    
    # 30 saniye sonra siparişi tamamlandı olarak işaretle
    def complete_order(order_id):
        import time
        time.sleep(30)
        order = Order.query.get(order_id)
        if order:
            order.status = 'completed'
            db.session.commit()
    
    import threading
    thread = threading.Thread(target=complete_order, args=(order.id,))
    thread.start()
    
    flash('Siparişiniz başarıyla oluşturuldu', 'success')
    return redirect(url_for('orders'))

@app.route('/orders')
@login_required
def orders():
    user_orders = Order.query.filter_by(user_id=current_user.id).all()
    return render_template('orders.html', orders=user_orders)

@app.route('/add_review/<int:item_id>', methods=['POST'])
@login_required
def add_review(item_id):
    rating = int(request.form['rating'])
    comment = request.form['comment']
    
    # Kullanıcının daha önce yorum yapıp yapmadığını kontrol et
    existing_review = Review.query.filter_by(
        user_id=current_user.id,
        menu_item_id=item_id
    ).first()
    
    if existing_review:
        existing_review.rating = rating
        existing_review.comment = comment
        existing_review.created_at = datetime.utcnow()
    else:
        review = Review(
            user_id=current_user.id,
            menu_item_id=item_id,
            rating=rating,
            comment=comment
        )
        db.session.add(review)
    
    # Menü öğesinin ortalama puanını güncelle
    menu_item = MenuItem.query.get(item_id)
    menu_item.update_rating()
    
    db.session.commit()
    flash('Değerlendirmeniz başarıyla eklendi', 'success')
    return redirect(url_for('menu_item_detail', item_id=item_id))

# Admin routes
@app.route('/admin/restaurants')
@login_required
def admin_restaurants():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    restaurants = Restaurant.query.all()
    return render_template('admin/restaurants.html', restaurants=restaurants)

@app.route('/admin/add_restaurant', methods=['GET', 'POST'])
@login_required
def add_restaurant():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        restaurant = Restaurant(
            name=request.form['name'],
            address=request.form['address'],
            phone=request.form['phone']
        )
        db.session.add(restaurant)
        db.session.commit()
        return redirect(url_for('admin_restaurants'))
    
    return render_template('admin/add_restaurant.html')

@app.route('/admin/restaurant/<int:restaurant_id>/add_menu_item', methods=['GET', 'POST'])
@login_required
def admin_add_menu_item(restaurant_id):
    if not current_user.is_admin:
        flash('Bu sayfaya erişim yetkiniz yok.', 'danger')
        return redirect(url_for('index'))
    
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    
    if request.method == 'POST':
        menu_item = MenuItem(
            name=request.form['name'],
            description=request.form['description'],
            price=float(request.form['price']),
            category=request.form['category'],  # Kategori eklendi
            restaurant_id=restaurant_id
        )
        
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                menu_item.image = url_for('static', filename=f'uploads/{filename}')
        
        db.session.add(menu_item)
        db.session.commit()
        flash('Menü öğesi başarıyla eklendi.', 'success')
        return redirect(url_for('admin_edit_restaurant', restaurant_id=restaurant_id))
    
    return render_template('admin/add_menu_item.html', restaurant=restaurant)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Kullanıcı adı ve e-posta kontrolü
        if username != current_user.username:
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash('Bu kullanıcı adı zaten kullanılıyor.', 'danger')
                return redirect(url_for('profile'))

        if email != current_user.email:
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                flash('Bu e-posta adresi zaten kullanılıyor.', 'danger')
                return redirect(url_for('profile'))

        # Şifre değişikliği kontrolü
        if current_password and new_password and confirm_password:
            if not check_password_hash(current_user.password, current_password):
                flash('Mevcut şifreniz yanlış.', 'danger')
                return redirect(url_for('profile'))
            
            if new_password != confirm_password:
                flash('Yeni şifreler eşleşmiyor.', 'danger')
                return redirect(url_for('profile'))
            
            current_user.password = generate_password_hash(new_password)

        # Profil bilgilerini güncelle
        current_user.username = username
        current_user.email = email
        current_user.phone = phone
        current_user.address = address

        try:
            db.session.commit()
            flash('Profil bilgileriniz başarıyla güncellendi.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Profil güncellenirken bir hata oluştu.', 'danger')

        return redirect(url_for('profile'))

    # Kullanıcının siparişlerini getir
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.order_time.desc()).all()
    return render_template('profile.html', orders=orders)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                current_user.profile_image = filename
        
        current_user.username = request.form.get('username')
        current_user.email = request.form.get('email')
        current_user.address = request.form.get('address')
        current_user.phone = request.form.get('phone')
        
        if request.form.get('current_password'):
            if current_user.check_password(request.form.get('current_password')):
                if request.form.get('new_password') == request.form.get('confirm_password'):
                    current_user.set_password(request.form.get('new_password'))
                else:
                    flash('Yeni şifreler eşleşmiyor')
                    return redirect(url_for('edit_profile'))
            else:
                flash('Mevcut şifre yanlış')
                return redirect(url_for('edit_profile'))
        
        db.session.commit()
        flash('Profil başarıyla güncellendi')
        return redirect(url_for('profile'))
    
    return render_template('edit_profile.html')

@app.route('/search')
def search():
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    rating = request.args.get('rating', '')
    
    restaurants = Restaurant.query
    
    if query:
        restaurants = restaurants.filter(Restaurant.name.ilike(f'%{query}%'))
    if category:
        restaurants = restaurants.filter(Restaurant.category == category)
    if rating:
        restaurants = restaurants.filter(Restaurant.rating >= float(rating))
    
    restaurants = restaurants.all()
    
    return render_template('index.html', restaurants=restaurants, 
                         query=query, category=category, rating=rating)

@app.route('/orders/filter')
@login_required
def filter_orders():
    status = request.args.get('status', '')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    orders = Order.query.filter_by(user_id=current_user.id)
    
    if status:
        orders = orders.filter_by(status=status)
    if start_date:
        orders = orders.filter(Order.order_time >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        orders = orders.filter(Order.order_time <= datetime.strptime(end_date, '%Y-%m-%d'))
    
    orders = orders.order_by(Order.order_time.desc()).all()
    
    return render_template('orders.html', orders=orders)

@app.route('/admin/restaurant/<int:restaurant_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_restaurant(restaurant_id):
    if not current_user.is_admin:
        flash('Bu sayfaya erişim yetkiniz yok.', 'danger')
        return redirect(url_for('index'))
    
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    
    if request.method == 'POST':
        restaurant.name = request.form['name']
        restaurant.address = request.form['address']
        restaurant.phone = request.form['phone']
        
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                restaurant.image = url_for('static', filename=f'uploads/{filename}')
        
        db.session.commit()
        flash('Restoran başarıyla güncellendi.', 'success')
        return redirect(url_for('admin_restaurants'))
    
    menu_items = MenuItem.query.filter_by(restaurant_id=restaurant_id).all()
    return render_template('admin/edit_restaurant.html', restaurant=restaurant, menu_items=menu_items)

@app.route('/admin/menu_item/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_menu_item(item_id):
    if not current_user.is_admin:
        flash('Bu sayfaya erişim yetkiniz yok.', 'danger')
        return redirect(url_for('index'))
    
    menu_item = MenuItem.query.get_or_404(item_id)
    
    if request.method == 'POST':
        menu_item.name = request.form['name']
        menu_item.description = request.form['description']
        menu_item.price = float(request.form['price'])
        
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                menu_item.image = url_for('static', filename=f'uploads/{filename}')
        
        db.session.commit()
        flash('Menü öğesi başarıyla güncellendi.', 'success')
        return redirect(url_for('admin_edit_restaurant', restaurant_id=menu_item.restaurant_id))
    
    return render_template('admin/edit_menu_item.html', menu_item=menu_item)

@app.route('/admin/menu_item/<int:item_id>/delete', methods=['POST'])
@login_required
def admin_delete_menu_item(item_id):
    if not current_user.is_admin:
        flash('Bu işlem için yetkiniz yok.', 'danger')
        return redirect(url_for('index'))
    
    menu_item = MenuItem.query.get_or_404(item_id)
    restaurant_id = menu_item.restaurant_id
    
    # Delete the image file if it exists
    if menu_item.image:
        try:
            image_path = os.path.join(app.root_path, 'static', menu_item.image.replace('/', os.sep))
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            print(f"Error deleting image: {e}")
    
    db.session.delete(menu_item)
    db.session.commit()
    flash('Menü öğesi başarıyla silindi.', 'success')
    return redirect(url_for('admin_edit_restaurant', restaurant_id=restaurant_id))

@app.route('/admin/restaurant/<int:restaurant_id>/delete', methods=['POST'])
@login_required
def admin_delete_restaurant(restaurant_id):
    if not current_user.is_admin:
        flash('Bu işlem için yetkiniz yok.', 'danger')
        return redirect(url_for('index'))
    
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    
    # Önce menü öğelerini sil
    for menu_item in restaurant.menu_items:
        # Menü öğesinin resmini sil
        if menu_item.image:
            try:
                image_path = os.path.join(app.root_path, 'static', menu_item.image.replace('/', os.sep))
                if os.path.exists(image_path):
                    os.remove(image_path)
            except Exception as e:
                print(f"Error deleting menu item image: {e}")
        
        # Menü öğesine ait değerlendirmeleri sil
        Review.query.filter_by(menu_item_id=menu_item.id).delete()
        
        # Menü öğesini sil
        db.session.delete(menu_item)
    
    # Restoranın resmini sil
    if restaurant.image:
        try:
            image_path = os.path.join(app.root_path, 'static', restaurant.image.replace('/', os.sep))
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            print(f"Error deleting restaurant image: {e}")
    
    # Restoranı sil
    db.session.delete(restaurant)
    db.session.commit()
    
    flash('Restoran başarıyla silindi.', 'success')
    return redirect(url_for('admin_restaurants'))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

if __name__ == '__main__':
    with app.app_context():
        # Veritabanı şemasını güncelle
        try:
            # Eski tabloları sil
            db.drop_all()
            # Yeni şema ile tabloları oluştur
            db.create_all()
            print("Veritabanı şeması başarıyla güncellendi.")
        except Exception as e:
            print(f"Veritabanı güncelleme hatası: {e}")
    app.run(debug=True) 