import requests
import os
import smtplib
from fastapi import FastAPI
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
ua = UserAgent()

amazon_sde_last_seen_job_id = None
amazon_sa_last_seen_job_id = None
google_last_seen_job_id = None

def send_email(new_jobs, job_type):
    sender_email = os.getenv("SENDER_EMAIL")
    receiver_email = os.getenv("RECIPIENT_EMAIL")
    password = os.getenv("SENDER_PASSWORD")

    message = MIMEMultipart("alternative")
    message["Subject"] = f"New {job_type} Job Alert!"
    message["From"] = sender_email
    message["To"] = receiver_email

    text = f"Hi there,\n\nNew {job_type} jobs have been found:\n\n"
    html = f"""\
    <html>
      <body>
        <p>Hi there,</p>
        <p>New {job_type} jobs have been found:</p>
        <ul>
    """

    for job in new_jobs:
        job_title = job.get('title', '')
        job_id = job.get('id', '')
        job_link = job.get('link', '')
        text += f"- Title: {job_title}, Job ID: {job_id}, Link: {job_link}\n"
        html += f"<li>Title: {job_title}, Job ID: {job_id}, <a href='{job_link}'>Link</a></li>"

    html += """\
        </ul>
      </body>
    </html>
    """

    part1 = MIMEText(text, "plain")
    part2 = MIMEText(html, "html")

    message.attach(part1)
    message.attach(part2)

    smtp_server = "smtp.gmail.com"
    port = 587

    try:
        server = smtplib.SMTP(smtp_server, port)
        server.starttls()
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, message.as_string())
        print(f"Email for {job_type} sent successfully!")
    except Exception as e:
        print(f"Error sending email for {job_type}: {e}")
    finally:
        server.quit()

def amazon_process_jobs(job_type, url, last_seen_id_global_name):
    global sde_last_seen_job_id, sa_last_seen_job_id

    try:
        headers = {"User-Agent": ua.random}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        jobs_data = response.json()
        jobs = jobs_data.get("jobs", [])

        if not jobs:
            print(f"No {job_type} jobs found in response.")
            return

        last_seen_id = globals()[last_seen_id_global_name]
        latest_job_id = jobs[0].get('id_icims')

        if last_seen_id is None:
            globals()[last_seen_id_global_name] = latest_job_id
            print(f"Initial {job_type} job list populated. Latest job ID: {latest_job_id}")
            return

        if latest_job_id == last_seen_id:
            print(f"No new {job_type} jobs found.")
            return

        new_jobs_raw = []
        for job in jobs:
            if job.get('id_icims') == last_seen_id:
                break
            new_jobs_raw.append(job)

        if new_jobs_raw:
            new_jobs_raw.reverse()
            new_jobs_formatted = [
                {
                    "id": job.get('id_icims'),
                    "title": job.get('title'),
                    "link": f"https://www.amazon.jobs{job.get('job_path')}"
                } for job in new_jobs_raw
            ]
            send_email(new_jobs_formatted, job_type)
            globals()[last_seen_id_global_name] = latest_job_id
            print(f"{len(new_jobs_raw)} new {job_type} jobs found and email sent.")
        else:
            print(f"No new {job_type} jobs found.")
            globals()[last_seen_id_global_name] = latest_job_id

    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch {job_type} jobs: {e}")

def google_process_jobs(job_type, url, last_seen_id_global_name):
    global google_last_seen_job_id
    try:
        headers = {"User-Agent": ua.random}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        job_list = soup.find("ul", class_="spHGqe")

        if not job_list:
            print(f"No {job_type} jobs found in response.")
            return

        jobs = job_list.find_all("li", class_="lLd3Je")
        if not jobs:
            print(f"No {job_type} job items found in response.")
            return

        last_seen_id = globals()[last_seen_id_global_name]
        latest_job_id = jobs[0]['ssk'].split(':')[-1]

        if last_seen_id is None:
            globals()[last_seen_id_global_name] = latest_job_id
            print(f"Initial {job_type} job list populated. Latest job ID: {latest_job_id}")
            return

        if latest_job_id == last_seen_id:
            print(f"No new {job_type} jobs found.")
            return

        new_jobs_raw = []
        for job in jobs:
            job_id = job['ssk'].split(':')[-1]
            if job_id == last_seen_id:
                break
            new_jobs_raw.append(job)

        if new_jobs_raw:
            new_jobs_raw.reverse()
            new_jobs_formatted = []
            for job in new_jobs_raw:
                job_id = job['ssk'].split(':')[-1]
                title = job.find("h3", class_="QJPWVe").text.strip()
                link_suffix = job.find("a", class_="WpHeLc")['href']
                link = f"https://www.google.com/about/careers/applications/{link_suffix}"
                new_jobs_formatted.append({"id": job_id, "title": title, "link": link})
            
            send_email(new_jobs_formatted, job_type)
            globals()[last_seen_id_global_name] = latest_job_id
            print(f"{len(new_jobs_raw)} new {job_type} jobs found and email sent.")
        else:
            print(f"No new {job_type} jobs found.")
            globals()[last_seen_id_global_name] = latest_job_id

    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch {job_type} jobs: {e}")
    except Exception as e:
        print(f"An error occurred while processing {job_type} jobs: {e}")

def fetch_and_process_amazon_sde_jobs():
    sde_url = os.getenv("AMAZON_SDE_URL")
    amazon_process_jobs("SDE", sde_url, "amazon_sde_last_seen_job_id")

def fetch_and_process_amazon_sa_jobs():
    sa_url = os.getenv("AMAZON_SA_URL")
    amazon_process_jobs("SA", sa_url, "amazon_sa_last_seen_job_id")

def fetch_and_process_google_jobs():
    google_url = os.getenv("GOOGLE_URL")
    google_process_jobs("Google", google_url, "google_last_seen_job_id")

scheduler = BackgroundScheduler()
scheduler.add_job(fetch_and_process_amazon_sde_jobs,    'interval', hours=1, jitter=180, next_run_time=datetime.now())
scheduler.add_job(fetch_and_process_amazon_sa_jobs,     'interval', hours=1, jitter=240, next_run_time=datetime.now() + timedelta(minutes=15))
scheduler.add_job(fetch_and_process_google_jobs, 'interval', hours=1, jitter=300, next_run_time=datetime.now() + timedelta(minutes=30))

@app.on_event("startup")
def start_scheduler():
    scheduler.start()

@app.on_event("shutdown")
def shutdown_scheduler():
    scheduler.shutdown()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/check-jobs")
def check_jobs_endpoint():
    fetch_and_process_amazon_sde_jobs()
    fetch_and_process_amazon_sa_jobs()
    fetch_and_process_google_jobs()
    return {"message": "Job checks for SDE, SA, and Google initiated."}
