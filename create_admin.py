from app import app, db, User

def create_admin():
    with app.app_context():
        # Admin kullanıcısı var mı kontrol et
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            # Admin kullanıcısı oluştur
            admin = User(
                username='admin',
                email='admin@example.com',
                is_admin=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Admin kullanıcısı başarıyla oluşturuldu!")
            print("Kullanıcı adı: admin")
            print("Şifre: admin123")
        else:
            print("Admin kullanıcısı zaten mevcut.")

if __name__ == '__main__':
    create_admin() 