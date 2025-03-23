import time
import random
import csv
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager

class MicrosoftJobScraper:
    def __init__(self, chromedriver_path=None, headless=False):
     
        self.base_url = "https://careers.microsoft.com/us/en/search-results"
        self.chromedriver_path = chromedriver_path
        self.headless = headless
        self.results = []
        self.driver = None

    def setup_driver(self):
        """Setup and configure Chrome WebDriver"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--log-level=3") 
        
        # Add a realistic user agent
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
        
        # Prevent detection
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        if self.chromedriver_path:
            service = Service(executable_path=self.chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            # Use webdriver-manager to handle driver installation
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        
       
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })
        
        return driver

    def build_search_url(self, keyword, location):
        """Build the Microsoft careers search URL with the given parameters"""
        # Microsoft's career site uses a different URL structure now
        # We'll use their search results page and apply filters
        base_url = "https://careers.microsoft.com/us/en/search-results"
        return base_url

    def navigate_to_search_results(self, keyword, location):
        """Navigate to search results page and apply filters"""
        self.driver.get(self.build_search_url(keyword, location))
        
        print(f"Navigating to Microsoft careers and searching for {keyword} in {location}...")
        
        try:
            # Wait for the search page to load
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input#keyword-search"))
            )
            
            # Enter keyword in search box
            keyword_input = self.driver.find_element(By.CSS_SELECTOR, "input#keyword-search")
            keyword_input.clear()
            keyword_input.send_keys(keyword)
            
            # Wait a moment for potential autocomplete
            time.sleep(1)
            
            # Try to find and select the location filter
            try:
                location_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-ph-at-id='jobs-location-filter']"))
                )
                location_button.click()
                
                # Wait for location dropdown to appear
                time.sleep(1)
                
                # Find and select the location
                location_option = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, f"//span[contains(text(), '{location}')]"))
                )
                location_option.click()
                
                # Close the dropdown if needed
                try:
                    apply_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Apply')]"))
                    )
                    apply_button.click()
                except:
                    pass
            except Exception as e:
                print(f"Could not set location filter: {str(e)}")
                
            # Click search button
            search_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-ph-at-id='jobs-search-button']"))
            )
            search_button.click()
            
            # Wait for results to load
            time.sleep(5)
            
            # Check if we have results
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.job-card, div.jobs-list, div[data-ph-at-id='job-list']"))
                )
                print("Search results loaded successfully")
                return True
            except TimeoutException:
                print("No search results found or page failed to load results")
                return False
                
        except Exception as e:
            print(f"Error navigating to search results: {str(e)}")
            return False

    def extract_total_jobs(self):
        """Extract the total number of jobs from the results page"""
        try:
            # Different possible selectors for job count
            selectors = [
                "//h2[contains(text(), 'result') or contains(text(), 'job') or contains(text(), 'showing')]",
                "//div[contains(text(), 'Showing') or contains(text(), 'results')]",
                "//span[contains(@class, 'result') and contains(text(), 'result')]",
                "//div[contains(@class, 'result-count')]"
            ]
            
            for selector in selectors:
                try:
                    element = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    text = element.text
                    import re
                    # Try to extract a number from the text
                    matches = re.findall(r'\d+', text)
                    if matches:
                        # Take the largest number as the total job count
                        return max(int(num) for num in matches)
                except:
                    continue
                    
            # If we can't find the total, count the job cards
            job_cards = self.driver.find_elements(By.CSS_SELECTOR, "div.job-card, div[data-ph-at-id='job-tile']")
            if job_cards:
                return len(job_cards)
                
            return 0
        except Exception as e:
            print(f"Error extracting total jobs: {str(e)}")
            return 0

    def extract_job_cards(self):
        """Extract job cards from the current page"""
        job_cards = []
        
        try:
            # Wait for job cards to load with multiple possible selectors
            for selector in ["div.job-card", "div[data-ph-at-id='job-tile']", "div.jobs-list > div", "li.search-result-item"]:
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    job_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if job_elements:
                        print(f"Found {len(job_elements)} job cards using selector: {selector}")
                        break
                except:
                    continue
            else:
                print("No job cards found with any selector")
                return []
            
            for job_element in job_elements:
                try:
                    # Extract job title with different possible selectors
                    job_title = None
                    for title_selector in [
                        ".//h3", 
                        ".//h2",
                        ".//a[contains(@data-ph-at-id, 'job-title')]",
                        ".//div[contains(@class, 'title')]",
                        ".//a[contains(@class, 'job-title')]"
                    ]:
                        try:
                            title_element = job_element.find_element(By.XPATH, title_selector)
                            job_title = title_element.text.strip()
                            if job_title:
                                break
                        except:
                            continue
                    
                    if not job_title:
                        job_title = "Unknown Title"
                    
                    # Extract location with different possible selectors
                    location = None
                    for location_selector in [
                        ".//span[contains(@class, 'location')]",
                        ".//span[contains(text(), ',')]",
                        ".//div[contains(@class, 'location')]",
                        ".//span[contains(@data-ph-id, 'location')]"
                    ]:
                        try:
                            location_element = job_element.find_element(By.XPATH, location_selector)
                            location = location_element.text.strip()
                            if location:
                                break
                        except:
                            continue
                            
                    if not location:
                        location = "Unknown Location"
                    
                    # Extract posting date
                    days_ago = None
                    for date_selector in [
                        ".//span[contains(text(), 'ago')]",
                        ".//span[contains(@class, 'date')]",
                        ".//div[contains(@class, 'date')]",
                        ".//span[contains(@data-ph-id, 'date')]"
                    ]:
                        try:
                            date_element = job_element.find_element(By.XPATH, date_selector)
                            days_ago = date_element.text.strip()
                            if days_ago:
                                break
                        except:
                            continue
                            
                    if not days_ago:
                        days_ago = "Unknown Date"
                    
                    # Extract job URL
                    job_url = None
                    try:
                        url_element = job_element.find_element(By.TAG_NAME, "a")
                        job_url = url_element.get_attribute("href")
                    except:
                        # Try to find the job ID and construct a URL
                        try:
                            job_id = job_element.get_attribute("data-job-id")
                            if job_id:
                                job_url = f"https://careers.microsoft.com/us/en/job/{job_id}"
                        except:
                            job_url = "Unknown URL"
                    
                    job_cards.append({
                        "title": job_title,
                        "location": location,
                        "days_ago": days_ago,
                        "company": "Microsoft",
                        "url": job_url
                    })
                    
                except Exception as e:
                    print(f"Error extracting job card data: {str(e)}")
                    continue
                    
            return job_cards
        except Exception as e:
            print(f"Error extracting job cards: {str(e)}")
            return []

    def go_to_next_page(self):
        """Navigate to the next page of results"""
        try:
            # Try different selectors for next page button
            for next_selector in [
                "//button[contains(@aria-label, 'Next page') or contains(@aria-label, 'next page')]",
                "//a[contains(@aria-label, 'Next page') or contains(@aria-label, 'next page')]",
                "//button[contains(text(), 'Next')]",
                "//a[contains(text(), 'Next')]",
                "//li[contains(@class, 'next')]/a",
                "//div[contains(@class, 'pagination')]//li[last()]/a",
                "//button[contains(@class, 'next')]"
            ]:
                try:
                    next_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, next_selector))
                    )
                    
                    # Check if the next button is disabled
                    disabled = next_button.get_attribute("disabled") or "disabled" in next_button.get_attribute("class") or "disabled" in next_button.get_attribute("aria-disabled")
                    
                    if disabled:
                        return False
                    
                    # Scroll to the button to ensure it's visible
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                    time.sleep(1)
                    
                    # Click the button
                    next_button.click()
                    
                    # Wait for the page to load
                    time.sleep(3)
                    
                    # Verify that we're on a new page
                    try:
                        WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "div.job-card, div[data-ph-at-id='job-tile']"))
                        )
                        return True
                    except:
                        print("Failed to load next page content")
                        return False
                        
                except NoSuchElementException:
                    continue
                except TimeoutException:
                    continue
                except Exception as e:
                    print(f"Error with next button selector {next_selector}: {str(e)}")
                    continue
                    
            # If we get here, we couldn't find/click any next button
            print("No next page button found or all pages have been scraped")
            return False
            
        except Exception as e:
            print(f"Error navigating to next page: {str(e)}")
            return False

    def scrape_jobs(self, keyword, location, max_pages=5):
        """Scrape jobs matching the keyword and location"""
        all_jobs = []
        
        try:
            self.driver = self.setup_driver()
            
            # Navigate to search results
            success = self.navigate_to_search_results(keyword, location)
            
            if not success:
                print("Failed to load search results")
                self.driver.quit()
                return all_jobs
            
            # Extract total jobs (if possible)
            total_jobs = self.extract_total_jobs()
            if total_jobs > 0:
                print(f"Found approximately {total_jobs} jobs. Starting to scrape...")
            else:
                print("Could not determine the total number of jobs. Starting to scrape anyway...")
            
            # Scrape the first page
            current_page = 1
            print(f"Scraping page {current_page}...")
            
            jobs_on_page = self.extract_job_cards()
            all_jobs.extend(jobs_on_page)
            print(f"Scraped {len(jobs_on_page)} jobs from page {current_page}")
            
            # Scrape additional pages
            while current_page < max_pages:
                # Add a random delay between page navigations
                delay = random.uniform(2.0, 5.0)
                time.sleep(delay)
                
                # Try to go to the next page
                if self.go_to_next_page():
                    current_page += 1
                    print(f"Scraping page {current_page}...")
                    
                    # Extract jobs from the new page
                    jobs_on_page = self.extract_job_cards()
                    all_jobs.extend(jobs_on_page)
                    print(f"Scraped {len(jobs_on_page)} jobs from page {current_page}")
                else:
                    print("No more pages available")
                    break
            
            self.results = all_jobs
            return all_jobs
            
        except Exception as e:
            print(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            # Make sure to close the driver
            if self.driver:
                self.driver.quit()

    def save_to_csv(self, filename=None):
        """Save results to a CSV file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"microsoft_jobs_{timestamp}.csv"
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['title', 'company', 'location', 'days_ago', 'url']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for job in self.results:
                    writer.writerow(job)
            
            print(f"Results saved to {filename}")
            print(f"Found a total of {len(self.results)} jobs")
            return True
        except Exception as e:
            print(f"Error saving results: {str(e)}")
            return False

# Function to run the scraper
def run_microsoft_scraper(keyword, location, max_pages=5, output_file=None, chromedriver_path=None, headless=False):
    scraper = MicrosoftJobScraper(chromedriver_path, headless)
    jobs = scraper.scrape_jobs(keyword, location, max_pages)
    
    if output_file:
        scraper.save_to_csv(output_file)
    else:
        scraper.save_to_csv()
        
    return jobs

# Example usage
if __name__ == "__main__":
    keyword = "Software Engineer"
    location = "Austin"
    output_file = f"{location}_{keyword.replace(' ', '_')}.csv"
    
    # If you have a specific chromedriver path, use it
    # Otherwise, webdriver-manager will handle it
    # chromedriver_path = "/Users/srikar/Desktop/KRIGNAL/chromedriver"
    chromedriver_path = None
    
    jobs = run_microsoft_scraper(
        keyword=keyword, 
        location=location, 
        max_pages=3, 
        output_file=output_file,
        chromedriver_path=chromedriver_path,
        headless=False  # Set to True for headless mode
    )
    print(f"Scraped {len(jobs)} Microsoft {keyword} jobs in {location}")