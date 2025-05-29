# Use an appropriate base image for web scraping.
FROM debian:bookworm-slim

# Set environment variables for non-interactive apt-get
ENV DEBIAN_FRONTEND=noninteractive

# Install common dependencies and Python 3.11
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    # Crucial for creating virtual environments
    python3-venv \
    wget \
    gnupg \
    unzip \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome browser and its dependencies
RUN apt-get update && apt-get install -y \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgdk-pixbuf2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxss1 \
    libxtst6 \
    lsb-release \
    xdg-utils \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Add Google Chrome's official repository and install
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/trusted.gpg.d/google-chrome.gpg \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Determine the installed Chrome version to pick the correct ChromeDriver.
RUN CHROME_VERSION=$(google-chrome --product-version | cut -d . -f 1) \
    && echo "Detected Chrome version: $CHROME_VERSION" \
    && CHROMEDRIVER_VERSION=$(wget -qO- "https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_${CHROME_VERSION}" | tr -d '\n') \
    && echo "Matching ChromeDriver version: $CHROMEDRIVER_VERSION" \
    && wget -q https://storage.googleapis.com/chrome-for-testing-public/${CHROMEDRIVER_VERSION}/linux64/chromedriver-linux64.zip -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /usr/local/bin/ \
    && mv /usr/local/bin/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && rm -rf /usr/local/bin/chromedriver-linux64 /tmp/chromedriver.zip \
    && chmod +x /usr/local/bin/chromedriver

# Set the working directory in the container
WORKDIR /app

# --- CHANGES START HERE ---

# Create a virtual environment
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV

# Activate the virtual environment for subsequent commands
# This ensures that pip installs into the venv and Python runs from it
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt into the virtual environment
RUN pip install --no-cache-dir -r requirements.txt

# --- CHANGES END HERE ---

# Copy the rest of your application code into the container
COPY . .

# Command to run your application when the container starts
# The virtual environment's python is now on PATH, so `python` will refer to it.
CMD ["python", "main.py"]