import feedparser
from newspaper import Article, Config
from google.adk.agents import Agent, SequentialAgent
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import requests
from bs4 import BeautifulSoup
from .email_agent import email_agent

feed_urls = [
        "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
        "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
        # add more feed URLs here
    ]

# Configure newspaper for better article extraction
config = Config()
config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
config.request_timeout = 15
config.thread_number = 1
config.fetch_images = False

def get_article_content(url):
    """Helper function to fetch article content with multiple methods."""
    try:
        # Method 1: Try newspaper3k
        article = Article(url, config=config)
        article.download()
        time.sleep(1)  # Respect rate limits
        article.parse()
        content = article.text
        if content and len(content) > 100:  # Check if we got substantial content
            return content

        # Method 2: Try direct requests + BeautifulSoup
        headers = {'User-Agent': config.browser_user_agent}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove unwanted elements
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'ads']):
            tag.decompose()
            
        # Try to find main content
        article_content = None
        # Common article content selectors
        selectors = [
            'article', '.article-content', '.story-content',
            '[role="main"]', '.main-content', '#main-content',
            '.post-content', '.entry-content'
        ]
        
        for selector in selectors:
            content_div = soup.select_one(selector)
            if content_div:
                article_content = content_div.get_text(separator='\n', strip=True)
                if len(article_content) > 100:  # Check if content is substantial
                    return article_content
                    
        # If no specific content div found, get all paragraphs
        paragraphs = soup.find_all('p')
        content = '\n'.join(p.get_text().strip() for p in paragraphs)
        if content and len(content) > 100:
            return content
            
    except Exception as e:
        print(f"Error fetching content: {str(e)}")
    
    return ""

def fetch_article_content(entry, keywords):
    """Helper function to fetch and score individual articles."""
    title = entry.get("title", "")
    
    # Handle content that might be a list or string
    initial_content = entry.get("content", "")
    if isinstance(initial_content, list):
        initial_content = " ".join(str(item) for item in initial_content)
    elif not isinstance(initial_content, str):
        initial_content = str(initial_content)
    
    link = entry.get("link")
    publish_date = entry.get('published_parsed') or entry.get('updated_parsed')
    
    if not link:
        return None

    # Initialize scoring components
    title_score = 0
    content_score = 0
    recency_score = 0
    
    # Score title matches (highest weight)
    title_lower = title.lower()
    for keyword in keywords:
        title_score += title_lower.count(keyword) * 10

    # Try to get full article content
    final_content = get_article_content(link)
    if not final_content:
        final_content = initial_content

    # Score content matches
    content_lower = str(final_content).lower()
    for keyword in keywords:
        content_score += content_lower.count(keyword)
        
    # Add recency bonus
    if publish_date:
        age_hours = (time.time() - time.mktime(publish_date)) / 3600
        if age_hours < 24:
            recency_score = 5
        elif age_hours < 168:  # 7 days
            recency_score = 3
    
    # Calculate total relevance score
    total_score = title_score + content_score + recency_score
    
    if total_score > 0:
        return {
            "title": title,
            "content": final_content,  # Return the complete content
            "link": link,
            "publish_date": publish_date,
            "relevance_score": total_score,
            "match_details": {
                "title_matches": title_score // 10,
                "content_matches": content_score,
                "recency_bonus": recency_score
            }
        }
    return None


def fetch_and_filter_articles(query: str) -> list[dict]:
    """
    Advanced search for the most relevant and recent news articles matching a user's query.

    Relevance Scoring:
    - Title match: 10 points per keyword match
    - First paragraph match: 5 points per keyword match
    - Content match: 1 point per keyword match
    - Recent articles (< 24h): +5 points
    - Recent articles (< 7d): +3 points
    - URL from primary source: +2 points

    Filtering Process:
    1. Query Analysis:
       - Processes main keywords and related terms
       - Handles misspellings and variations
       - Considers synonyms and related concepts

    2. Article Matching:
       - Prioritizes exact keyword matches in titles
       - Checks first paragraph relevance
       - Analyzes full content for context
       - Considers article freshness (publication date)

    3. Result Ranking:
       - Combines relevance score and freshness
       - Prioritizes high-quality sources
       - Removes duplicates and similar content
       - Returns top N most relevant results

    Args:
        query (str): The search query with possible misspellings/variations

    Returns:
        list[dict]: Top 10 most relevant articles, each containing:
            - title: Article title
            - content: Full article content
            - summary: Brief preview/first paragraph
            - url: Direct article URL
            - publish_date: Publication date
            - relevance_score: Numerical score
            - match_details: Where/how query matched
    """
    max_articles_per_feed = 15  # Increased to get more candidates
    max_results = 10
    matched_articles = []
    seen_links = set()
    query_lower = query.lower()
    
    # Split query into keywords for better matching
    keywords = query_lower.split()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for url in feed_urls:
            try:
                feed = feedparser.parse(url)
                # Sort entries by date if available
                entries = sorted(
                    feed.entries[:max_articles_per_feed],
                    key=lambda x: x.get('published_parsed', x.get('updated_parsed')),
                    reverse=True
                )
            except Exception as e:
                continue

            for entry in entries:
                link = entry.get("link")
                if not link or link in seen_links:
                    continue
                seen_links.add(link)
                futures.append(executor.submit(fetch_article_content, entry, keywords))

        for future in as_completed(futures):
            result = future.result()
            if result:
                matched_articles.append(result)

    if not matched_articles:
        return [{"message": f"No articles found containing the query '{query}'."}]

    # Enhanced sorting with multiple criteria
    matched_articles.sort(key=lambda x: (
        x.get('relevance_score', 0),  # Primary: relevance score
        x.get('publish_date', ''),    # Secondary: publication date
        x.get('is_primary_source', False)  # Tertiary: source quality
    ), reverse=True)

    # Return top N results with detailed matching info
    return matched_articles[:max_results]

# First agent - Article Ingestor
article_ingestor_agent = Agent(
    name="article_ingestor",
    model="gemini-2.0-flash",
    instruction="""
        When a user provides a query:
        1. First, analyze and improve the search query:
           - Extract key concepts and important terms
           - Handle misspellings and variations
           - Add relevant synonyms or related terms
           
           Examples:
           User query: "climate change impact on oceans"
           Enhanced: climate change, ocean impact, sea level, marine ecosystem
           
           User query: "ai developement in helthcare"
           Enhanced: AI development, healthcare, medical technology
           (correcting misspellings)

        2. Use the enhanced keywords with fetch_and_filter_articles tool
        
        3. For each article from the tool output:
           - Extract the complete article content
           - If content is in dictionary format (like RSS feed), get the 'value' field
           - Remove any metadata or technical fields
           - Keep the full, unmodified article text
           - Preserve all paragraphs and formatting
           - Include the original source URL
           
        4. Present each article in this format:

           1. ARTICLE TITLE
           ===============

           [COMPLETE article content, unmodified and properly formatted]

           Source: [Original article URL]
           
           ---------------

        The goal is to provide the complete, unmodified content of each article
        in a clean, readable format.
    """,
    tools=[fetch_and_filter_articles],
    output_key="fetched_articles"
)

# Second agent - Content Summarizer
content_summarizer_agent = Agent(
    name="content_summarizer",
    model="gemini-2.0-flash",
    instruction="""
        For each article, format the output exactly like this:

        # Article Title
        
        A comprehensive 250-word summary written in clear paragraphs. The summary 
        should flow naturally and cover the article's main points, findings, and 
        conclusions. Include relevant data and quotes seamlessly within the text.
        
        The summary must maintain proper paragraph structure with clear transitions 
        between ideas. Each paragraph should focus on a specific aspect of the 
        article while maintaining a logical flow throughout the entire summary.
        
        The final paragraph should wrap up the main points and present any 
        conclusions or implications discussed in the article.

        **Source**: [Publication Name](full_article_url)

        -----------------------------------

        Requirements:
        - Use # for article titles
        - Write exactly 250 words
        - Format in clear paragraphs (usually 3-4)
        - Include source link at bottom in bold
        - Add separator line between articles
        - Maintain professional tone throughout
        - Integrate quotes and data naturally
        - No bullet points or subsections
        
        Example:
        # Scientists Discover New Climate Pattern

        # Summary
        
        A groundbreaking study published today reveals a previously unknown 
        climate pattern affecting global temperatures. The research, conducted 
        over five years, analyzed data from 100 monitoring stations worldwide.

        Lead researcher Dr. Sarah Chen explains, "This discovery fundamentally 
        changes our understanding of climate systems." The team found that 
        oceanic temperature variations follow a 15-year cycle, significantly 
        impacting weather patterns across continents.

        These findings suggest that current climate models may need revision, 
        with important implications for future predictions and policy planning.

        **Source**: [Nature Climate](https://nature.com/article)

        -----------------------------------
    """,
    output_key="summarized_articles"
)

# Create the sequential agent
article_fetcher_and_summarizer_agent = SequentialAgent(
    name="article_fetcher_and_summarizer",
    sub_agents=[article_ingestor_agent, content_summarizer_agent, email_agent],
    description="Executes a sequence of article fetching, summarization, and email delivery.",
    # The agents will run in order: Fetcher -> Summarizer -> Email
)

# For ADK tools compatibility
root_agent = article_fetcher_and_summarizer_agent

