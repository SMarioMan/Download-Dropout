# Use a slim Python image for a smaller footprint
FROM python:3.11-slim

# Install ffmpeg and curl
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Install Python dependencies
# Using direct pip install to keep it "minimal" without a requirements.txt
RUN pip install --no-cache-dir requests beautifulsoup4

# Download the latest yt-dlp binary directly to ensures it's up to date
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && \
    chmod a+rx /usr/local/bin/yt-dlp

# Copy the script into the container
COPY download_dropout.py .

# Create a volume for the downloads and state files
VOLUME ["/app/downloads", "/app/config"]

# Set the entrypoint to run the script
# We point output-dir to our volume
ENTRYPOINT ["python", "/app/download_dropout.py", "--output-dir", "/app/downloads"]

# Build
# docker build -t dropout-downloader .


# Mount the directory with cookies.txt and archive.txt in the config folder
# Mount a target downloads folder

# Linux
# docker run -it -v "$(pwd)"/config:/app/config -v "$(pwd)/Dropout":/app/downloads dropout-downloader

# Windows:
# docker run -it -v "%cd%/config:/app/config" -v "%cd%/Dropout:/app/downloads" dropout-downloader

# PowerShell:
# docker run -it -v "${PWD}/config:/app/config" -v "${PWD}/Dropout:/app/downloads" dropout-downloader