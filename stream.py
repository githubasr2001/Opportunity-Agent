import streamlit as st
import pandas as pd
import time
import os
import logging
import re
from datetime import datetime
from io import StringIO
import base64

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Function to create a download link for dataframes
def get_csv_download_link(df, filename):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">Download CSV</a>'
    return href

# Function to scroll and load all jobs
def scroll_to_load_all(driver, max_scrolls=20, wait_time=1.5):
    """
    Scroll the page to load all content with a maximum number of scrolls.
    For Greenhouse-based sites like ZScaler.
    """
    scrolls = 0
    last_height = driver.execute_script("return document.body.scrollHeight")
    last_job_count = 0
    consecutive_no_change = 0

    logger.info("Starting to scroll to load all content...")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    status_text.text("Scrolling to load all jobs...")

    while scrolls < max_scrolls:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(wait_time)
        
        # Try clicking 'Load More' buttons if available
        try:
            load_more_buttons = driver.find_elements(By.XPATH, 
                "//button[contains(text(), 'Load More') or contains(text(), 'View More')]")
            if load_more_buttons:
                for button in load_more_buttons:
                    if button.is_displayed() and button.is_enabled():
                        driver.execute_script("arguments[0].click();", button)
                        logger.info("Clicked 'Load More' button")
                        time.sleep(wait_time + 1)
        except Exception as e:
            logger.info(f"No 'Load More' button found or error clicking it: {e}")

        new_height = driver.execute_script("return document.body.scrollHeight")
        job_count = len(driver.find_elements(By.CLASS_NAME, "opening"))

        logger.info(f"Scroll {scrolls+1}: Height {last_height} → {new_height}, Jobs found: {job_count}")
        status_text.text(f"Scrolling to load all jobs... Found {job_count} jobs so far")
        progress_bar.progress((scrolls + 1) / max_scrolls)

        if new_height == last_height and job_count == last_job_count:
            consecutive_no_change += 1
            logger.info(f"No change detected ({consecutive_no_change}/3)")
            if consecutive_no_change >= 3:
                logger.info("No more content loading after multiple scrolls. Stopping scroll operation.")
                break
        else:
            consecutive_no_change = 0

        last_height = new_height
        last_job_count = job_count
        scrolls += 1

    status_text.text(f"Completed scrolling. Found {last_job_count} job listings.")
    progress_bar.progress(1.0)
    logger.info(f"Completed scrolling after {scrolls} scrolls. Found approximately {last_job_count} job items.")
    return last_job_count

# Function to extract job information from the ZScaler page
def extract_job_listings_zscaler(driver):
    """
    Extract job listings (Title, Location, Department, Link) from ZScaler Greenhouse page.
    """
    jobs_data = []
    
    try:
        job_elements = driver.find_elements(By.CLASS_NAME, "opening")
        logger.info(f"Found {len(job_elements)} job elements on page")
        
        status_text = st.empty()
        status_text.text(f"Extracting details for {len(job_elements)} job listings...")
        progress_bar = st.progress(0)
        
        for index, job in enumerate(job_elements):
            try:
                a_elem = job.find_element(By.TAG_NAME, "a")
                title = a_elem.text.strip()
                link = a_elem.get_attribute("href")
                
                # Extract location
                location = "Not specified"
                try:
                    location_elem = job.find_element(By.CLASS_NAME, "location")
                    location_text = location_elem.text.strip()
                    if location_text and len(location_text) < 50 and "footer" not in location_text.lower():
                        location = location_text
                except NoSuchElementException:
                    pass
                
                department = "Not specified"
                try:
                    department_elem = job.find_element(By.CLASS_NAME, "department")
                    department = department_elem.text.strip()
                except:
                    pass
                
                if title and title.strip() and link and link.strip():
                    is_duplicate = any(existing_job["Title"] == title and existing_job["Link"] == link 
                                     for existing_job in jobs_data)
                    if not is_duplicate:
                        jobs_data.append({
                            "Title": title,
                            "Location": location,
                            "Department": department,
                            "Link": link
                        })
                
                progress_bar.progress((index + 1) / len(job_elements))
                status_text.text(f"Extracting job details... {index+1}/{len(job_elements)}")
                
            except (StaleElementReferenceException, Exception) as e:
                logger.error(f"Error extracting job details for job {index+1}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error finding job elements: {e}")
    
    return jobs_data

# Function to handle pagination for ZScaler
def handle_pagination(driver, max_pages=10):
    """
    Handle pagination for ZScaler Greenhouse site.
    """
    page = 1
    all_jobs = []
    
    logger.info("Starting pagination handling for ZScaler...")
    
    status_text = st.empty()
    status_text.text("Handling pagination...")
    progress_bar = st.progress(0)
    
    while page <= max_pages:
        logger.info(f"Processing page {page}")
        status_text.text(f"Processing page {page} of {max_pages}...")
        
        jobs_on_page = extract_job_listings_zscaler(driver)
        all_jobs.extend(jobs_on_page)
        logger.info(f"Found {len(jobs_on_page)} jobs on page {page}")
        
        next_button = None
        try:
            next_buttons = driver.find_elements(By.XPATH, 
                "//a[contains(text(), 'Next') or contains(@class, 'next') or contains(@aria-label, 'Next')]")
            for button in next_buttons:
                if button.is_displayed() and "disabled" not in button.get_attribute("class"):
                    next_button = button
                    break
        except Exception:
            pass
        
        if not next_button:
            logger.info("No next page button found. Reached last page.")
            break
            
        try:
            driver.execute_script("arguments[0].click();", next_button)
            logger.info("Clicked next page button")
            time.sleep(3)
            page += 1
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "opening"))
            )
            progress_bar.progress(page / max_pages)
        except Exception as e:
            logger.error(f"Error clicking next page: {e}")
            break
            
    status_text.text(f"Pagination complete. Found {len(all_jobs)} total jobs.")
    progress_bar.progress(1.0)
    return all_jobs

# Function to handle different types of popups
def handle_popups(driver):
    try:
        popup_selectors = [
            "//button[contains(text(), 'Accept')]", 
            "//button[contains(text(), 'I agree')]",
            "//button[contains(@id, 'accept')]",
            "//button[contains(@class, 'accept')]",
            "//button[contains(text(), 'Continue')]",
            "//button[contains(text(), 'Got it')]",
            "//button[contains(text(), 'Close')]",
            "//button[@aria-label='Close']",
            "//div[contains(@class, 'cookie')]//button",
            "//div[contains(@id, 'consent')]//button"
        ]
        
        for xpath in popup_selectors:
            try:
                buttons = driver.find_elements(By.XPATH, xpath)
                for button in buttons:
                    if button.is_displayed():
                        button.click()
                        logger.info(f"Clicked popup/cookie button with xpath: {xpath}")
                        time.sleep(1)
            except Exception:
                continue
                
        # Handle alert popups if present
        try:
            alert = driver.switch_to.alert
            alert.accept()
            logger.info("Accepted alert popup")
        except Exception:
            pass
            
    except Exception as e:
        logger.warning(f"Error handling popups: {e}")

# Main ZScaler job scraper function
def scrape_zscaler_jobs(search_keyword="", max_pages=10, headless=True):
    """
    Scrape ZScaler jobs using the Greenhouse job board.
    """
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36')
    
    os.makedirs('screenshots', exist_ok=True)
    
    driver = None
    jobs_data = []

    try:
        with st.spinner('Setting up Chrome Driver...'):
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            driver.set_page_load_timeout(30)
        
        base_url = "https://boards.greenhouse.io/zscaler"
        logger.info(f"Scraping jobs from ZScaler" + (f", filtering by keyword '{search_keyword}'" if search_keyword else ""))
        
        with st.spinner('Opening Zscaler careers page...'):
            driver.get(base_url)
            handle_popups(driver)
        
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "opening"))
            )
            logger.info("Job listings loaded successfully")
            st.success("Job listings page loaded successfully!")
        except TimeoutException:
            logger.warning("Timed out waiting for job listings to load")
            st.error("Timed out waiting for job listings to load. Please try again.")
            
        # If a search keyword is provided, use the search box if available
        if search_keyword:
            try:
                with st.spinner(f'Searching for "{search_keyword}"...'):
                    search_box = driver.find_element(By.ID, "search_keywords")
                    if search_box:
                        search_box.clear()
                        search_box.send_keys(search_keyword)
                        search_box.send_keys(Keys.RETURN)
                        time.sleep(3)
                        logger.info(f"Searched for '{search_keyword}'")
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CLASS_NAME, "opening"))
                        )
            except NoSuchElementException:
                logger.info("No search box found. Will filter results after scraping.")
                st.info("No search box found. Will filter results after scraping all jobs.")
        
        scroll_to_load_all(driver)
        
        all_jobs = handle_pagination(driver, max_pages=max_pages)
        logger.info(f"Collected {len(all_jobs)} total jobs after pagination")
        
        # If search keyword filtering wasn't done using the search box, filter the results here
        if search_keyword and all_jobs:
            filtered_jobs = [job for job in all_jobs if search_keyword.lower() in job["Title"].lower()]
            logger.info(f"Filtered from {len(all_jobs)} to {len(filtered_jobs)} jobs matching '{search_keyword}'")
            all_jobs = filtered_jobs
        
        jobs_data = all_jobs
        logger.info(f"Total jobs found: {len(jobs_data)}")
        
    except Exception as e:
        logger.error(f"Error during scraping from ZScaler: {e}")
        st.error(f"Error during scraping: {str(e)}")

    finally:
        if driver:
            driver.quit()

    return jobs_data

# Helper function to gather text under a heading (until the next heading or end of section)
def get_section_text(driver, heading_element):
    """
    Gathers all text (e.g., paragraphs, lists) between the given heading_element
    and the next section heading.
    """
    text_list = []
    current_elem = heading_element
    
    # Get the parent element of the heading (usually a <p> tag)
    parent = driver.execute_script("return arguments[0].parentElement", current_elem)
    
    # Start from the parent's next sibling
    current_elem = parent
    
    while True:
        # Move to the next sibling
        next_elem = driver.execute_script("return arguments[0].nextElementSibling", current_elem)
        if not next_elem:
            # No more siblings, end of content
            break
            
        # Check if we've reached the next section (usually marked by another <p><strong> structure)
        try:
            if next_elem.tag_name.lower() == "p" and next_elem.find_element(By.TAG_NAME, "strong"):
                strong_text = next_elem.find_element(By.TAG_NAME, "strong").text.strip().lower()
                if "qualifications" in strong_text or "what" in strong_text:
                    break
        except:
            pass
            
        # Check if we've reached a different section type
        if next_elem.tag_name.lower() == "div" and "content-nav" in next_elem.get_attribute("class"):
            break
            
        # Otherwise, gather its text
        text_list.append(next_elem.text.strip())
        current_elem = next_elem
        
    # Join all pieces of text
    return "\n".join(t for t in text_list if t)

# Function to extract job descriptions from URLs
def extract_job_descriptions(df, max_jobs=None):
    """
    Extract detailed job descriptions from each URL in the dataframe
    """
    if max_jobs is None:
        max_jobs = len(df)
    else:
        max_jobs = min(max_jobs, len(df))
    
    # Create new columns to store extracted sections
    result_df = df.copy()
    if 'Minimum Qualifications' not in result_df.columns:
        result_df['Minimum Qualifications'] = ""
    if 'Preferred Qualifications' not in result_df.columns:
        result_df['Preferred Qualifications'] = ""
    
    # Setup Chrome driver
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    driver = None
    try:
        with st.spinner('Setting up Chrome Driver for description extraction...'):
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        
        for i in range(max_jobs):
            link = result_df.loc[i, 'Link']
            status_text.text(f"Processing job {i+1}/{max_jobs}: {result_df.loc[i, 'Title']}")
            logger.info(f"Processing {i+1}/{max_jobs}: {link}")
            
            # Open the job link
            driver.get(link)
            time.sleep(3)  # Adjust if needed, or use WebDriverWait
            
            # Find all <strong> elements
            strong_elements = driver.find_elements(By.TAG_NAME, "strong")
            
            # Placeholders for the extracted text
            min_qual_text = ""
            pref_qual_text = ""
            
            # Check each strong element's text to see if it matches the sections we need
            for strong in strong_elements:
                heading_text = strong.text.strip().lower()
                
                # Check for minimum qualifications heading
                if ("what we're looking for" in heading_text or "minimum qualifications" in heading_text):
                    min_qual_text = get_section_text(driver, strong)
                    logger.info(f"Found minimum qualifications: {min_qual_text[:100]}...")
                    
                # Check for preferred qualifications heading
                elif ("what will make you stand out" in heading_text or "preferred qualifications" in heading_text):
                    pref_qual_text = get_section_text(driver, strong)
                    logger.info(f"Found preferred qualifications: {pref_qual_text[:100]}...")
            
            # Store the results back into the DataFrame
            result_df.at[i, 'Minimum Qualifications'] = min_qual_text
            result_df.at[i, 'Preferred Qualifications'] = pref_qual_text
            
            progress_bar.progress((i + 1) / max_jobs)
            
    except Exception as e:
        logger.error(f"Error during description extraction: {e}")
        st.error(f"Error extracting job descriptions: {str(e)}")
        
    finally:
        if driver:
            driver.quit()
            
    status_text.text("Description extraction complete!")
    return result_df

# Streamlit UI functions
def create_filters_section(df):
    """
    Create filter widgets for the dataframe
    """
    st.subheader("Filter Jobs")
    
    # Get unique values for filtering
    locations = ["All"] + sorted(df["Location"].unique().tolist())
    
    # Create filters
    selected_location = st.selectbox("Filter by Location", locations)
    
    # Apply filters
    filtered_df = df.copy()
    if selected_location != "All":
        filtered_df = filtered_df[filtered_df["Location"] == selected_location]
    
    # Title search
    search_title = st.text_input("Search in job titles")
    if search_title:
        filtered_df = filtered_df[filtered_df["Title"].str.contains(search_title, case=False, na=False)]
    
    # Display filter results stats
    st.write(f"Showing {len(filtered_df)} of {len(df)} jobs")
    
    return filtered_df

def display_results_table(df):
    """
    Display results in a nice table with expandable rows
    """
    if df.empty:
        st.warning("No jobs found matching your criteria.")
        return

    st.subheader("Job Results")
    
    # Create a dataframe for display (simplified view)
    display_df = df[["Title", "Location"]].copy()
    
    # Display the table with selectable rows
    selected_indices = st.multiselect(
        "Select jobs to view details:",
        range(len(display_df)),
        format_func=lambda i: f"{display_df.iloc[i]['Title']} - {display_df.iloc[i]['Location']}"
    )
    
    # Show selected job details
    if selected_indices:
        for idx in selected_indices:
            job = df.iloc[idx]
            
            st.subheader(f"{job['Title']}")
            st.write(f"**Location:** {job['Location']}")
            
            # Create columns for job details
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Minimum Qualifications")
                if job["Minimum Qualifications"]:
                    st.write(job["Minimum Qualifications"])
                else:
                    st.write("No minimum qualifications specified.")
            
            with col2:
                st.subheader("Preferred Qualifications")
                if job["Preferred Qualifications"]:
                    st.write(job["Preferred Qualifications"])
                else:
                    st.write("No preferred qualifications specified.")
            
            st.markdown(f"[Apply for this position]({job['Link']})")
            st.markdown("---")

# Function to load and display image
def display_logo():
    """
    Display the Zscaler logo image
    """
    try:
        # Check if the file exists
        if os.path.exists("Zscaler.png"):
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.image("Zscaler.png", use_container_width=True)
        else:
            logger.warning("Logo image 'Zscaler.png' not found")
    except Exception as e:
        logger.error(f"Error displaying logo: {e}")

# Streamlit app
def main():
    import base64
    
    st.set_page_config(
        page_title="Zscaler Job Scraper",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Add custom CSS
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #0077b6;
        text-align: center;
        margin-bottom: 20px;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #023e8a;
        margin-top: 30px;
        margin-bottom: 10px;
    }
    .info-box {
        background-color: #e9f5f9;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 20px;
    }
    .stProgress > div > div > div {
        background-color: #0077b6;
    }
    .logo-container {
        display: flex;
        justify-content: center;
        margin-bottom: 20px;
    }
    .header-container {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 30px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Display logo and header in a container with better styling
    st.markdown('<div class="header-container">', unsafe_allow_html=True)
    
    # Display the logo
    display_logo()
    
    # Header section
    st.markdown('<div class="main-header">🔍 Zscaler Job Scraper</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; font-size: 1.2rem; color: #555;">Find and analyze career opportunities at Zscaler</p>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Sidebar for configuration
    st.sidebar.title("Configuration")
    
    # Scraper options
    mode = st.sidebar.radio("Mode", ["Scrape New Jobs", "Use Existing CSV"])
    
    if mode == "Scrape New Jobs":
        st.markdown('<div class="sub-header">Job Search Parameters</div>', unsafe_allow_html=True)
        
        with st.form("search_form"):
            search_keyword = st.text_input("Job Title Keyword (leave empty for all jobs)")
            max_pages = st.slider("Maximum Pages to Scrape", 1, 20, 5)
            headless_mode = st.checkbox("Run in Headless Mode", value=True)
            extract_desc = st.checkbox("Extract Job Descriptions", value=True)
            max_desc_jobs = st.number_input("Maximum Jobs to Extract Descriptions", min_value=1, max_value=50, value=5)
            
            submit_button = st.form_submit_button("Start Scraping")
        
        if submit_button:
            with st.spinner('Scraping jobs from Zscaler...'):
                start_time = time.time()
                jobs_data = scrape_zscaler_jobs(search_keyword, max_pages, headless_mode)
                
                if jobs_data:
                    # Convert to DataFrame
                    df = pd.DataFrame(jobs_data)
                    
                    # Display initial results
                    st.success(f"Found {len(df)} jobs matching your criteria!")
                    st.dataframe(df[['Title', 'Location', 'Department']])
                    
                    # Extract descriptions if requested
                    if extract_desc and len(df) > 0:
                        st.markdown('<div class="sub-header">Extracting Job Descriptions</div>', unsafe_allow_html=True)
                        
                        with st.spinner('Extracting job descriptions...'):
                            df = extract_job_descriptions(df, max_jobs=max_desc_jobs)
                            st.success(f"Extracted descriptions for {min(max_desc_jobs, len(df))} jobs!")
                    
                    # Save results to CSV
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    keyword_slug = search_keyword.replace(' ', '_') if search_keyword else 'all'
                    output_filename = f"zscaler_jobs_{keyword_slug}_{timestamp}.csv"
                    df.to_csv(output_filename, index=False, encoding='utf-8-sig')
                    
                    # Provide download link
                    st.markdown(f"Results saved to '{output_filename}'")
                    csv = df.to_csv(index=False)
                    b64 = base64.b64encode(csv.encode()).decode()
                    href = f'<a href="data:file/csv;base64,{b64}" download="{output_filename}">Download Results CSV</a>'
                    st.markdown(href, unsafe_allow_html=True)
                    
                    # Display filtered results
                    st.markdown('<div class="sub-header">Explore Results</div>', unsafe_allow_html=True)
                    filtered_df = create_filters_section(df)
                    display_results_table(filtered_df)
                    
                    elapsed_time = time.time() - start_time
                    st.info(f"Process completed in {elapsed_time:.2f} seconds")
                else:
                    st.error("No jobs found. Try different search parameters.")
    
    else:  # Use Existing CSV
        st.markdown('<div class="sub-header">Upload Existing CSV</div>', unsafe_allow_html=True)
        
        uploaded_file = st.file_uploader("Choose a CSV file with job data", type="csv")
        
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)
                st.success(f"Loaded CSV with {len(df)} jobs.")
                
                # Check if descriptions already exist
                has_descriptions = 'Minimum Qualifications' in df.columns and 'Preferred Qualifications' in df.columns
                
                if not has_descriptions:
                    extract_desc = st.checkbox("Extract Job Descriptions", value=True)
                    max_desc_jobs = st.number_input("Maximum Jobs to Extract Descriptions", min_value=1, max_value=50, value=5)
                    
                    if extract_desc and st.button("Extract Descriptions"):
                        with st.spinner('Extracting job descriptions...'):
                            df = extract_job_descriptions(df, max_jobs=max_desc_jobs)
                            st.success(f"Extracted descriptions for {min(max_desc_jobs, len(df))} jobs!")
                            
                            # Provide download link for updated data
                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                            output_filename = f"zscaler_jobs_with_descriptions_{timestamp}.csv"
                            csv = df.to_csv(index=False)
                            b64 = base64.b64encode(csv.encode()).decode()
                            href = f'<a href="data:file/csv;base64,{b64}" download="{output_filename}">Download Updated CSV with Descriptions</a>'
                            st.markdown(href, unsafe_allow_html=True)
                
                # Display filtered results
                st.markdown('<div class="sub-header">Explore Results</div>', unsafe_allow_html=True)
                filtered_df = create_filters_section(df)
                display_results_table(filtered_df)
                
            except Exception as e:
                st.error(f"Error loading CSV: {str(e)}")
    
    # About section in sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### About")
    st.sidebar.info(
        "This app scrapes job listings from Zscaler's career page and allows "
        "extraction of detailed job descriptions and qualifications. "
        "You can search for specific job titles, filter by location, and save results for later use."
    )
    
    st.sidebar.markdown("### Instructions")
    st.sidebar.markdown(
        """
        1. **Scrape New Jobs**: Search and scrape fresh job listings.
        2. **Use Existing CSV**: Upload previously scraped job data.
        3. Filter results by location or job title.
        4. Select jobs to view detailed descriptions.
        5. Download results as CSV for future use.
        """
    )

if __name__ == "__main__":
    main()