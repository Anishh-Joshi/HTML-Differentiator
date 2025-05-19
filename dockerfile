FROM python:3.9-bullseye

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory
WORKDIR /var/task

# Copy only the necessary files
COPY app.py requirements.txt ./

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy additional project files if needed
COPY . .

# Set the entrypoint for AWS Lambda
CMD ["python", "app.py", "initate_cron"]
