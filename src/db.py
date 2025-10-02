import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from the .env file in the same directory
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def test_connection():
    """Test the Supabase connection"""
    try:
        # Try to list tables to see what exists
        response = supabase.rpc('get_tables').execute()
        print("✅ Database connection successful!")
        print(f"Connection URL: {url}")
        print(f"Available data: {response.data}")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {str(e)}")
        print(f"URL: {url}")
        print(f"Key: {key[:20]}..." if key else "No key found")
        
        # Try a different approach - just check if we can connect
        try:
            # Try to query a system table
            response = supabase.table('pg_tables').select('tablename').execute()
            print("Alternative connection test succeeded")
            return True
        except Exception as e2:
            print(f"Alternative test also failed: {str(e2)}")
            return False

if __name__ == "__main__":
    test_connection()