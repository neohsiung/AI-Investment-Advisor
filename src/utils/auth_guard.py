"""
Authentication Guard Utility

Provides a unified authentication gate for all Streamlit pages.
Prevents UI flash by blocking execution until auth status is confirmed.
"""
import streamlit as st
from src.auth import auth_manager


def require_authentication():
    """
    Unified authentication gate for all pages.
    
    Blocks execution until authentication is confirmed:
    - LOADING: Shows spinner and stops execution
    - UNAUTHENTICATED: Shows login message and stops execution  
    - AUTHENTICATED: Returns user object
    
    Returns:
        dict: User information with 'email', 'name', etc.
        
    Raises:
        st.stop(): Execution stops if not authenticated
    """
    auth_status = auth_manager.check_login()
    
    if auth_status == "LOADING":
        # Cookie synchronization in progress
        st.info("🔄 驗證中... (Authenticating...)", icon="🔄")
        st.stop()
        
    elif auth_status == "UNAUTHENTICATED" or auth_status is False:
        # Not authenticated - show login UI
        st.warning("⚠️ 請先登入 (Please login first)")
        auth_manager.login()  # Show the login button
        st.stop()
    
    # Authenticated - return user object
    user = auth_manager.get_current_user()
    
    # Safety check
    if not user or 'email' not in user:
        st.error("Authentication Error: 無效的使用者資料 (Invalid user data)")
        auth_manager.logout()
        st.stop()

    # v4.0 Patch: Resolve UUID identity
    from src.repositories.user_repository import AlchemyUserRepository
    from src.utils.logger import setup_logger
    logger = setup_logger("AuthGuard")
    
    user_repo = AlchemyUserRepository()
    
    email = user['email']
    user_record = user_repo.get_by_identity('email', email)
    
    if not user_record:
        # Auto-create user if first login
        logger.info(f"Creating new user for {email}")
        new_uuid = user_repo.create_user(email, name=user.get('name'))
        user['id'] = new_uuid
    else:
        user['id'] = user_record['id']
        logger.debug(f"Resolved user {email} to ID: {user['id']}")
        
    return user
