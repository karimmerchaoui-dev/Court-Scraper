import os
import pickle


class SessionManager:
    def __init__(self, session_dir="./sessions"):
        self.session_dir = session_dir
        os.makedirs(session_dir, exist_ok=True)

    def save_session(self, driver, session_name):
        """Save cookies and session data."""
        session_file = os.path.join(self.session_dir, f"{session_name}.pkl")

        session_data = {
            'cookies': driver.get_cookies(),
            'local_storage': driver.execute_script("return window.localStorage;"),
            'session_storage': driver.execute_script("return window.sessionStorage;"),
            'current_url': driver.current_url
        }

        with open(session_file, 'wb') as f:
            pickle.dump(session_data, f)

        print(f"✅ Session saved: {session_file}")

    def load_session(self, driver, session_name):
        """Load cookies and session data."""
        session_file = os.path.join(self.session_dir, f"{session_name}.pkl")

        if not os.path.exists(session_file):
            print(f"❌ Session not found: {session_file}")
            return False

        with open(session_file, 'rb') as f:
            session_data = pickle.load(f)

        # Navigate to the domain first (required for cookies)
        driver.get(session_data['current_url'])

        # Restore cookies
        for cookie in session_data['cookies']:
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                print(f"⚠️ Could not add cookie: {e}")

        # Restore localStorage
        if session_data.get('local_storage'):
            for key, value in session_data['local_storage'].items():
                driver.execute_script(f"window.localStorage.setItem('{key}', '{value}');")

        # Restore sessionStorage
        if session_data.get('session_storage'):
            for key, value in session_data['session_storage'].items():
                driver.execute_script(f"window.sessionStorage.setItem('{key}', '{value}');")

        # Refresh to apply everything
        driver.refresh()
        print(f"✅ Session loaded: {session_file}")
        return True