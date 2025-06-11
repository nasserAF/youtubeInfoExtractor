# YouTube CC Extractor

## Overview
A Flask web application to extract closed captions and video information from YouTube URLs.

## Prerequisites
- Python 3.8+
- pip (Python package manager)

## Setup Instructions

1. Clone the repository
```bash
git clone https://github.com/yourusername/youtube-cc-extractor.git
cd youtube-cc-extractor
```

2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Set up YouTube API Key
- Go to [Google Cloud Console](https://console.cloud.google.com/)
- Create a new project
- Enable YouTube Data API v3
- Create credentials (API Key)
- Create a `.env` file in the project root
- Add your API key to the `.env` file:
```
YOUTUBE_API_KEY=your_api_key_here
```

5. Run the application
```bash
python app.py
```

## Features
- Extract video metadata
- Retrieve closed captions
- Supports multiple languages
- User-friendly dark-themed UI

## Security
- API key stored in environment variables
- `.env` file excluded from version control

## Contributing
1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License
[Specify your license here]
