#!/usr/bin/env python3
"""
Quick test script to run app with .env file loaded
"""
from dotenv import load_dotenv
import uvicorn

# Load .env file
load_dotenv()

# Run the app
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
