import os
from typing import Dict, List
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.adk.agents import Agent
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Predefined recipient email
RECIPIENT_EMAIL = "2022-bs-ai-006@tuf.edu.pk"

# Default SMTP settings
SMTP_CONFIG = {
    'server': os.getenv('SMTP_HOST', 'smtp.gmail.com'),
    'port': int(os.getenv('SMTP_PORT', '587')),
    'user': os.getenv('SMTP_USER', ''),
    'password': os.getenv('SMTP_PASSWORD', ''),
    'use_tls': True
}

def process_summarized_articles(summarized_articles: List[Dict]) -> List[Dict]:
    """
    Process and validate the summarized articles from the summarizer agent.
    
    Args:
        summarized_articles: Raw output from the summarizer agent
        
    Returns:
        List of processed and validated articles
    """
    processed_articles = []
    
    for article in summarized_articles:
        # Extract the required fields from the summarizer's output
        processed_article = {
            'title': article.get('title', ''),
            'summary': article.get('summary', ''),
            'link': article.get('link', ''),
            'source': article.get('source', 'Unknown Source'),
            'publish_date': article.get('publish_date', '')
        }
        
        # Only include articles with required fields
        if all([processed_article['title'], processed_article['summary'], processed_article['link']]):
            processed_articles.append(processed_article)
            
    return processed_articles

def format_html_email(articles: List[Dict]) -> str:
    """Format the articles into a nice HTML email template."""
    html = """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            .container { max-width: 800px; margin: 0 auto; padding: 20px; }
            .article { margin-bottom: 30px; border-bottom: 1px solid #eee; padding-bottom: 20px; }
            .article-title { color: #1a73e8; font-size: 24px; margin-bottom: 10px; }
            .article-summary { margin-bottom: 15px; white-space: pre-line; }
            .article-link { color: #1a73e8; text-decoration: none; }
            .article-link:hover { text-decoration: underline; }
            .header { background: #1a73e8; color: white; padding: 20px; margin-bottom: 30px; }
            .footer { text-align: center; margin-top: 30px; color: #666; }
            .metadata { font-size: 12px; color: #666; margin-top: 10px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Your Personalized News Summary</h1>
                <p style="font-size: 16px;">Here are your latest news articles based on your interests.</p>
            </div>
    """
    
    for article in articles:
        html += f"""
            <div class="article">
                <h2 class="article-title">{article['title']}</h2>
                <div class="article-summary">
                    {article['summary']}
                </div>
                <a href="{article['link']}" class="article-link">Read Full Article →</a>
                <div class="metadata">
                    Source: {article['source']}
                    {f"<br>Published: {article['publish_date']}" if article['publish_date'] else ''}
                </div>
            </div>
        """
    
    html += """
            <div class="footer">
                <p>This summary was generated automatically for you.</p>
                <p style="font-size: 12px;">To unsubscribe or modify your preferences, please reply to this email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html

def send_email(articles: str) -> Dict:
    """
    Send email with article summaries to the predefined recipient.
    
    Args:
        articles: JSON string containing array of article objects
        
    Returns:
        Dict containing status and message
    """
    try:
        # Parse the articles data
        if isinstance(articles, str):
            articles_list = json.loads(articles)
        else:
            articles_list = articles
            
        if not articles_list or not isinstance(articles_list, list):
            raise ValueError("Invalid articles data: Expected a list of articles")

        # Validate SMTP configuration
        if not SMTP_CONFIG['user'] or not SMTP_CONFIG['password']:
            raise ValueError("Email credentials not found. Please set SMTP_USER and SMTP_PASSWORD environment variables")
            
        # Create email message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'Climate Change News Summary'
        msg['From'] = f"News Agent <{SMTP_CONFIG['user']}>"
        msg['To'] = RECIPIENT_EMAIL
        
        # Create HTML content
        html = """
        <html>
        <head>
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    line-height: 1.6; 
                    max-width: 800px; 
                    margin: 0 auto; 
                    padding: 20px;
                }
                .article { 
                    margin-bottom: 30px; 
                    padding: 20px; 
                    border: 1px solid #eee;
                    border-radius: 5px;
                }
                .title { 
                    color: #2c5282; 
                    font-size: 24px;
                    margin-bottom: 15px;
                }
                .summary { 
                    color: #2d3748; 
                    margin: 15px 0;
                    white-space: pre-line;
                }
                .metadata {
                    color: #718096;
                    font-size: 14px;
                    margin-top: 10px;
                }
                .link { 
                    color: #4299e1; 
                    text-decoration: none;
                    display: inline-block;
                    margin-top: 10px;
                }
                .link:hover {
                    text-decoration: underline;
                }
            </style>
        </head>
        <body>
            <h1 style="color: #1a365d; text-align: center; margin-bottom: 30px;">
                Latest Climate Change News
            </h1>
        """
        
        for article in articles_list:
            html += f"""
            <div class="article">
                <h2 class="title">{article['title']}</h2>
                <div class="summary">{article['summary']}</div>
                <div class="metadata">
                    Source: {article['source']}
                    {f" | Published: {article['publish_date']}" if article.get('publish_date') else ''}
                </div>
                <a href="{article['link']}" class="link">Read full article →</a>
            </div>
            """
            
        html += """
            <div style="text-align: center; margin-top: 30px; color: #718096;">
                <p>This news summary was automatically generated for you.</p>
            </div>
        </body>
        </html>
        """
        
        # Attach HTML version
        msg.attach(MIMEText(html, 'html'))
        
        # Send email
        with smtplib.SMTP(SMTP_CONFIG['server'], SMTP_CONFIG['port']) as server:
            if SMTP_CONFIG['use_tls']:
                server.starttls()
            server.login(SMTP_CONFIG['user'], SMTP_CONFIG['password'])
            server.send_message(msg)
        
        return {
            "status": "success",
            "message": f"Email sent successfully to {RECIPIENT_EMAIL}",
            "articles_count": len(articles_list),
            "smtp_config": {
                "server": SMTP_CONFIG['server'],
                "port": SMTP_CONFIG['port'],
                "user": SMTP_CONFIG['user']
            }
        }
        
    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "message": f"Invalid JSON data: {str(e)}",
            "error_type": "JSONDecodeError"
        }
    except ValueError as e:
        return {
            "status": "error",
            "message": str(e),
            "error_type": "ValueError"
        }
    except smtplib.SMTPException as e:
        return {
            "status": "error",
            "message": f"SMTP error: {str(e)}",
            "error_type": "SMTPException",
            "smtp_config": {
                "server": SMTP_CONFIG['server'],
                "port": SMTP_CONFIG['port'],
                "user": SMTP_CONFIG['user']
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to send email: {str(e)}",
            "error_type": type(e).__name__
        }

# Create the email agent using Google ADK
email_agent = Agent(
    name="email_agent",
    model="gemini-2.0-flash",
    instruction="""
    This agent receives summarized_articles directly from the content_summarizer_agent.
    
    Required Environment Variables:
    - SMTP_USER: Your Gmail address
    - SMTP_PASSWORD: Your Gmail app password
    - SMTP_HOST: SMTP server (default: smtp.gmail.com)
    - SMTP_PORT: SMTP port (default: 587)
    
    Input: 
    - Takes 'summarized_articles' from previous agent
    - Format already contains:
        * title
        * summary
        * link
        * source
        * publish_date
    
    Process:
    1. Validates SMTP configuration
    2. Creates HTML email with formatting
    3. Sends to bs-ai-006@tuf.edu.pk
    
    The agent focuses on secure email delivery with proper error handling.
    """,
    tools=[send_email],
    output_key="email_status"
) 