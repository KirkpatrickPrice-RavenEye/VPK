#!/usr/bin/env python3
"""
Script to reset the admin user password and ensure account is active.
Run this inside the Docker container:
  docker compose exec backend python reset_admin.py
handy for when you lock yourself out... like I do...
"""

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User, UserRole

def reset_admin():
    db = SessionLocal()
    try:
        # Default admin credentials
        admin_email = "admin@example.com"
        new_password = "admin123"

        # Find admin user
        admin_user = db.query(User).filter(User.email == admin_email).first()

        if not admin_user:
            print(f"❌ Admin user not found: {admin_email}")
            print("Creating new admin user...")

            # Create admin user
            admin_user = User(
                email=admin_email,
                password_hash=get_password_hash(new_password),
                role=UserRole.ADMIN,
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            print(f"✅ Admin user created: {admin_email}")
            print(f"   Password: {new_password}")
        else:
            print(f"Found admin user: {admin_email}")
            print(f"   Current status: {'Active' if admin_user.is_active else 'Inactive'}")
            print(f"   Role: {admin_user.role.value}")

            # Reset password and ensure active
            admin_user.password_hash = get_password_hash(new_password)
            admin_user.is_active = True
            admin_user.role = UserRole.ADMIN
            db.commit()

            print(f"✅ Admin account reset successfully!")
            print(f"   Email: {admin_email}")
            print(f"   Password: {new_password}")
            print(f"   Status: Active")
            print(f"   Role: ADMIN")

    except Exception as e:
        print(f"❌ Error resetting admin account: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("VPK Admin Account Reset")
    print("=" * 60)
    reset_admin()
    print("=" * 60)
