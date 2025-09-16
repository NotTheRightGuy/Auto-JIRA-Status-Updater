from dotenv import load_dotenv
import requests
import os


def validate_bitbucket_token():
    """
    Validate Bitbucket token by testing authentication and permissions
    """
    load_dotenv()

    email = os.getenv("ATLASSIAN_EMAIL")
    token = os.getenv("BITBUCKET_TOKEN")

    # Check if credentials are loaded
    if not email or not token:
        print("Error: Missing credentials in .env file")
        print("Required: ATLASSIAN_EMAIL and BITBUCKET_TOKEN")
        return False

    print("Validating Bitbucket Token...")
    print(f"Email: {email}")
    print(f"Token: {token[:8]}{'*' * (len(token) - 8)}")
    print("-" * 50)

    auth = (email, token)
    results = {}

    # Test 1: Basic Authentication
    print("1. Testing basic authentication...")
    try:
        response = requests.get("https://api.bitbucket.org/2.0/user", auth=auth)

        if response.status_code == 200:
            user_data = response.json()
            print(f"Authentication successful!")
            print(f"User: {user_data.get('display_name', 'N/A')}")
            print(f"Email: {user_data.get('email', 'N/A')}")
            print(f"Username: {user_data.get('username', 'N/A')}")
            results["auth"] = True
        else:
            print(f"Authentication failed: {response.status_code}")
            print(f"Response: {response.text}")
            results["auth"] = False
            return False

    except Exception as e:
        print(f"Request failed: {str(e)}")
        results["auth"] = False
        return False

    # Test 2: Repository Access
    print("\n2.Testing repository access...")
    workspace = "inappad"
    repo_slug = "applift-app"

    try:
        repo_url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}"
        response = requests.get(repo_url, auth=auth)

        if response.status_code == 200:
            repo_data = response.json()
            print(f"Repository access successful!")
            print(f"Repo: {repo_data.get('full_name', 'N/A')}")
            print(f"Private: {repo_data.get('is_private', 'N/A')}")
            print(f"Updated: {repo_data.get('updated_on', 'N/A')[:10]}")
            results["repo_access"] = True
        elif response.status_code == 404:
            print(f"Repository not found or no access")
            print(f"Check if repository exists and you have permission")
            results["repo_access"] = False
        else:
            print(f"Repository access failed: {response.status_code}")
            print(f"Response: {response.text}")
            results["repo_access"] = False

    except Exception as e:
        print(f"Repository request failed: {str(e)}")
        results["repo_access"] = False

    # Test 3: Branches Access
    print("\n3. Testing branches access...")
    try:
        branches_url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}/refs/branches?pagelen=5"
        response = requests.get(branches_url, auth=auth)

        if response.status_code == 200:
            branches_data = response.json()
            branch_count = len(branches_data.get("values", []))
            total_size = branches_data.get("size", 0)

            print(f"Branches access successful!")
            print(f"Found {total_size} total branches")
            print(f"First {branch_count} branches:")

            for branch in branches_data.get("values", [])[:3]:
                print(f"      - {branch['name']}")

            results["branches_access"] = True
        else:
            print(f"Branches access failed: {response.status_code}")
            results["branches_access"] = False

    except Exception as e:
        print(f"Branches request failed: {str(e)}")
        results["branches_access"] = False

    # Test 4: Token Permissions
    print("\n4. Testing token permissions...")
    try:
        # Try to access app passwords endpoint to check token scope
        permissions_url = "https://api.bitbucket.org/2.0/user/permissions/repositories"
        response = requests.get(permissions_url, auth=auth)

        if response.status_code == 200:
            print("Token has repository permissions")
            results["permissions"] = True
        else:
            print("Limited token permissions (this might be okay)")
            results["permissions"] = False

    except Exception as e:
        print(f"Could not check permissions: {str(e)}")
        results["permissions"] = False

    # Summary
    print("\n" + "=" * 50)
    print("VALIDATION SUMMARY")
    print("=" * 50)

    total_tests = len(results)
    passed_tests = sum(results.values())

    print(f"Passed: {passed_tests}/{total_tests} tests")

    if results.get("auth", False):
        print("Token is VALID and working!")

        if results.get("repo_access", False) and results.get("branches_access", False):
            print("Ready to fetch branches from your repositories!")
        else:
            print("Token works but may have limited repository access")

        return True
    else:
        print("Token is INVALID or expired")
        print("\nTroubleshooting tips:")
        print(
            "   1. Check if ATLASSIAN_TOKEN is an App Password (not regular password)"
        )
        print("   2. Verify the App Password has 'Repositories: Read' permission")
        print("   3. Make sure ATLASSIAN_EMAIL matches your Bitbucket account")
        print(
            "   4. Create new App Password: https://bitbucket.org/account/settings/app-passwords/"
        )

        return False


def quick_token_check():
    """Quick one-liner token validation"""
    load_dotenv()

    email = os.getenv("ATLASSIAN_EMAIL")
    token = os.getenv("BITBUCKET_TOKEN")

    if not email or not token:
        print("Missing credentials")
        return False

    try:
        response = requests.get(
            "https://api.bitbucket.org/2.0/user", auth=(email, token)
        )
        if response.status_code == 200:
            user = response.json().get("display_name", "Unknown")
            print(f"Token is valid! Logged in as: {user}")
            return True
        else:
            print(f"Token invalid: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False


if __name__ == "__main__":
    print("Bitbucket Token Validator")
    print("========================\n")

    # Uncomment the line below for detailed validation
    # validate_bitbucket_token()

    # Uncomment the line below for quick validation
    quick_token_check()
