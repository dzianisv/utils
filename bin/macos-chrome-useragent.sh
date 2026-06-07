#!/bin/bash
#
# macos-chrome-useragent.sh
# Creates a macOS app wrapper for Chrome with a custom User Agent
#
# Usage:
#   ./macos-chrome-useragent.sh                    # Interactive mode
#   ./macos-chrome-useragent.sh --linux            # Chrome Dev with Linux UA
#   ./macos-chrome-useragent.sh --windows          # Chrome Dev with Windows UA
#   ./macos-chrome-useragent.sh --uninstall        # Remove created apps
#   ./macos-chrome-useragent.sh --custom "UA"      # Custom user agent string
#
# Examples:
#   ./macos-chrome-useragent.sh --linux
#   ./macos-chrome-useragent.sh --custom "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
#

set -e

# Configuration
CHROME_DEV_PATH="/Applications/Google Chrome Dev.app"
CHROME_PATH="/Applications/Google Chrome.app"

# User Agent strings (update version numbers as needed)
UA_LINUX="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
UA_WINDOWS="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
UA_ANDROID="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
UA_IPHONE="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Function to create the app wrapper
create_app() {
    local app_name="$1"
    local user_agent="$2"
    local source_chrome="$3"
    local app_path="/Applications/${app_name}.app"
    
    print_info "Creating ${app_name}..."
    
    # Check if source Chrome exists
    if [[ ! -d "$source_chrome" ]]; then
        print_error "Source Chrome not found: $source_chrome"
        exit 1
    fi
    
    # Remove existing app if present
    if [[ -d "$app_path" ]]; then
        print_warning "Removing existing ${app_name}..."
        rm -rf "$app_path"
    fi
    
    # Create app bundle structure
    mkdir -p "${app_path}/Contents/MacOS"
    mkdir -p "${app_path}/Contents/Resources"
    
    # Get the executable name from source
    local source_executable=$(basename "$source_chrome" .app)
    
    # Create launcher script
    cat > "${app_path}/Contents/MacOS/${app_name}" << EOF
#!/bin/bash
exec "${source_chrome}/Contents/MacOS/${source_executable}" \\
  --user-agent="${user_agent}" \\
  "\$@"
EOF
    
    chmod +x "${app_path}/Contents/MacOS/${app_name}"
    
    # Create Info.plist
    local bundle_id=$(echo "$app_name" | tr ' ' '.' | tr '[:upper:]' '[:lower:]')
    cat > "${app_path}/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>${app_name}</string>
    <key>CFBundleIconFile</key>
    <string>app.icns</string>
    <key>CFBundleIdentifier</key>
    <string>com.custom.${bundle_id}</string>
    <key>CFBundleName</key>
    <string>${app_name}</string>
    <key>CFBundleDisplayName</key>
    <string>${app_name}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF
    
    # Copy icon from source Chrome
    if [[ -f "${source_chrome}/Contents/Resources/app.icns" ]]; then
        cp "${source_chrome}/Contents/Resources/app.icns" "${app_path}/Contents/Resources/"
    fi
    
    # Register with Launch Services
    /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$app_path" 2>/dev/null || true
    
    print_success "Created: ${app_path}"
    print_info "User Agent: ${user_agent:0:60}..."
}

# Function to uninstall created apps
uninstall_apps() {
    print_info "Searching for Chrome User Agent wrapper apps..."
    
    local apps=(
        "/Applications/Google Chrome Dev Linux.app"
        "/Applications/Google Chrome Dev Windows.app"
        "/Applications/Google Chrome Dev Android.app"
        "/Applications/Google Chrome Dev iPhone.app"
        "/Applications/Google Chrome Linux.app"
        "/Applications/Google Chrome Windows.app"
        "/Applications/Google Chrome Android.app"
        "/Applications/Google Chrome iPhone.app"
    )
    
    local removed=0
    for app in "${apps[@]}"; do
        if [[ -d "$app" ]]; then
            print_warning "Removing: $app"
            rm -rf "$app"
            ((removed++))
        fi
    done
    
    if [[ $removed -eq 0 ]]; then
        print_info "No wrapper apps found to remove."
    else
        print_success "Removed $removed app(s)."
    fi
}

# Function to show interactive menu
show_menu() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║          Chrome User Agent Wrapper Creator                 ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Check available Chrome installations
    echo "Available Chrome installations:"
    [[ -d "$CHROME_DEV_PATH" ]] && echo "  [1] Google Chrome Dev"
    [[ -d "$CHROME_PATH" ]] && echo "  [2] Google Chrome"
    echo ""
    
    echo "Select Chrome version to wrap:"
    read -p "Enter choice (1 or 2): " chrome_choice
    
    case $chrome_choice in
        1) selected_chrome="$CHROME_DEV_PATH"; chrome_prefix="Google Chrome Dev" ;;
        2) selected_chrome="$CHROME_PATH"; chrome_prefix="Google Chrome" ;;
        *) print_error "Invalid choice"; exit 1 ;;
    esac
    
    echo ""
    echo "Select User Agent:"
    echo "  [1] Linux (Chrome on Linux x86_64)"
    echo "  [2] Windows (Chrome on Windows 10/11)"
    echo "  [3] Android (Chrome on Pixel)"
    echo "  [4] iPhone (Safari on iOS)"
    echo "  [5] Custom"
    echo ""
    read -p "Enter choice (1-5): " ua_choice
    
    case $ua_choice in
        1) 
            selected_ua="$UA_LINUX"
            app_name="${chrome_prefix} Linux"
            ;;
        2)
            selected_ua="$UA_WINDOWS"
            app_name="${chrome_prefix} Windows"
            ;;
        3)
            selected_ua="$UA_ANDROID"
            app_name="${chrome_prefix} Android"
            ;;
        4)
            selected_ua="$UA_IPHONE"
            app_name="${chrome_prefix} iPhone"
            ;;
        5)
            echo ""
            read -p "Enter custom User Agent string: " selected_ua
            read -p "Enter app name (e.g., 'Google Chrome Dev Custom'): " app_name
            ;;
        *)
            print_error "Invalid choice"
            exit 1
            ;;
    esac
    
    echo ""
    create_app "$app_name" "$selected_ua" "$selected_chrome"
    
    echo ""
    print_success "Done! You can now search for '${app_name}' in Spotlight."
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --linux           Create Chrome Dev with Linux User Agent"
    echo "  --windows         Create Chrome Dev with Windows User Agent"
    echo "  --android         Create Chrome Dev with Android User Agent"
    echo "  --iphone          Create Chrome Dev with iPhone/Safari User Agent"
    echo "  --custom \"UA\"     Create Chrome Dev with custom User Agent"
    echo "  --uninstall       Remove all created wrapper apps"
    echo "  --list-ua         List available User Agent strings"
    echo "  --help            Show this help message"
    echo ""
    echo "Without options, runs in interactive mode."
    echo ""
    echo "Examples:"
    echo "  $0 --linux"
    echo "  $0 --custom \"Mozilla/5.0 (Custom Agent)\""
}

# Function to list user agents
list_user_agents() {
    echo ""
    echo "Available User Agent strings:"
    echo ""
    echo "Linux:"
    echo "  $UA_LINUX"
    echo ""
    echo "Windows:"
    echo "  $UA_WINDOWS"
    echo ""
    echo "Android:"
    echo "  $UA_ANDROID"
    echo ""
    echo "iPhone/Safari:"
    echo "  $UA_IPHONE"
    echo ""
}

# Main script logic
main() {
    case "${1:-}" in
        --linux)
            create_app "Google Chrome Dev Linux" "$UA_LINUX" "$CHROME_DEV_PATH"
            ;;
        --windows)
            create_app "Google Chrome Dev Windows" "$UA_WINDOWS" "$CHROME_DEV_PATH"
            ;;
        --android)
            create_app "Google Chrome Dev Android" "$UA_ANDROID" "$CHROME_DEV_PATH"
            ;;
        --iphone)
            create_app "Google Chrome Dev iPhone" "$UA_IPHONE" "$CHROME_DEV_PATH"
            ;;
        --custom)
            if [[ -z "${2:-}" ]]; then
                print_error "Custom User Agent string required"
                echo "Usage: $0 --custom \"Your User Agent String\""
                exit 1
            fi
            read -p "Enter app name (default: 'Google Chrome Dev Custom'): " custom_name
            custom_name="${custom_name:-Google Chrome Dev Custom}"
            create_app "$custom_name" "$2" "$CHROME_DEV_PATH"
            ;;
        --uninstall)
            uninstall_apps
            ;;
        --list-ua)
            list_user_agents
            ;;
        --help|-h)
            show_usage
            ;;
        "")
            show_menu
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
}

main "$@"
