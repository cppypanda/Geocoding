# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
python run.py
```
The Flask application will start on `http://0.0.0.0:5000` with debug mode enabled.

### Testing
```bash
pytest
```
Run all tests. Test configuration is in `pytest.ini` with pythonpath set to current directory.

### Database Management
- Initialize databases: `python init_db.py`
- Initialize location types: `python init_location_types.py`  
- Set admin user: `python set_admin.py`
- View database contents: `python view_db.py`
- Database migration: `python migrate_db.py`

### Dependencies
Install required packages with:
```bash
pip install -r requirements.txt
```

## Architecture Overview

This is a Flask-based geocoding web application following a strict **three-layer architecture** as defined in `ARCHITECTURE.md`:

### 1. Routes Layer (`app/routes/`)
- **Purpose**: HTTP request handling and business flow orchestration
- **Key files**: 
  - `geocoding.py`: Main geocoding endpoints following waterfall logic
  - `auth.py`: Authentication routes
  - `user.py`: User management
  - `main.py`: General application routes
  - `payment_bp.py`: Payment processing
- **Rules**: 
  - Must NOT contain direct I/O operations or external API calls
  - Must NOT parse raw third-party API responses
  - Should delegate complex logic to services/utils layers

### 2. Services Layer (`app/services/`)
- **Purpose**: External API integration and third-party service adaptation
- **Key files**:
  - `geocoding_apis.py`: Geocoder classes for Amap, Baidu, Tianditu APIs
  - `llm_service.py`: AI/LLM integration 
  - `poi_search.py`: Point of interest search functionality
- **Rules**: 
  - Handles ALL external I/O (HTTP requests, database calls)
  - Standardizes third-party API responses into internal formats
  - Must NOT contain cross-service business logic

### 3. Utils Layer (`app/utils/`)
- **Purpose**: Pure computational functions and reusable algorithms
- **Key files**:
  - `address_processing.py`: Core confidence calculation algorithms
  - `geo_transforms.py`: Coordinate system transformations
  - `api_managers.py`: API key rotation and rate limiting
- **Rules**: 
  - Must be stateless pure functions
  - Must NOT contain any I/O operations
  - Should be independently testable

## Key Workflows

### Multi-Source Geocoding Flow
The application implements a sophisticated waterfall approach:
1. Route layer receives address input
2. Utils layer performs address completion and cleaning
3. Services layer calls geocoding APIs in priority order (Amap → Tianditu → Baidu)
4. Utils layer calculates confidence scores for results
5. Route layer selects winner and optionally enhances with reverse geocoding

### Database Schema
- **User data**: `database/user_data.db` (users, recharge orders, API keys)
- **Geocoding cache**: `database/geocoding.db` (location types, cached results)
- **API keys**: `database/api_keys.db` (third-party service keys)

## Special Considerations

### API Key Management
The application uses a sophisticated API key rotation system managed through `utils/api_managers.py`. Keys are automatically rotated when rate limits or quotas are exceeded.

### Context Logging
Custom logging with contextual information is implemented via `utils/log_context.py` and configured in the Flask app initialization.

### Static Files
Static files are served from the root `/static/` directory (not `app/static/`) due to file permission issues during development.

### Configuration
Main configuration is in `app/config.py` with additional constants in root `config.py`.

## Documentation References
- `ARCHITECTURE.md`: Detailed architectural principles and layer responsibilities  
- `docs/SOP_*.md`: Standard operating procedures for various geocoding workflows
- `docs/poi_search_documentation.md`: POI search functionality documentation