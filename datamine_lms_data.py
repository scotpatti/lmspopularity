from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from random import randint
from time import sleep

import time
import re
import json

# remove script tags from the text
def remove_scripts(text):
    return re.sub("<script.*?</script>", "", text, flags=re.DOTALL|re.IGNORECASE)

# remove style tags from the text
def remove_style_elements(text):
    return re.sub("<style.*?</style>", "", text ,flags=re.DOTALL|re.IGNORECASE)

# returns a list of anchor tags in a dictionary (anchor_text, url_link)
def retrieve_anchor_dict(driver):
    anchors = driver.find_elements(By.TAG_NAME, "a")
    anchorList = {}
    for anchor in anchors:
        a_href = anchor.get_attribute("href")
        a_text = re.sub(r"[\r\n\t]+", "", re.sub(r" +", " ", anchor.get_attribute("text"))).strip()
        if a_href and a_text: 
            anchorList[a_text] = a_href
    return anchorList

# Assumption -> Sites don't mention names of LMS that they don't use. Hence, 
# lms_name is a guess (a good guess) and we can look to see if it is the only 
# guess in the keyword counts. 
# Checks to see if an LMS is mentioned on this page!
def retrieve_keyword_dict(text):
    keyword_dict = {}
    flag_found = False
    lms_name = ""
    for keyword in LMS_NAMES:
        results = re.findall(keyword, text, re.IGNORECASE)
        if results is not None:
            if len(results) == 0:
                keyword_dict[keyword] = 0
            else:
                keyword_dict[keyword] = len(results)
                flag_found = True
                lms_name = keyword
    return keyword_dict, flag_found, lms_name
    

# A way to get CANDIDATE_KEYS_REGEX without having to create it every time.
def get_candidate_keywords_regex():
    global CANDIDATE_KEYWORDS_REGEX
    if not CANDIDATE_KEYWORDS_REGEX:
        CANDIDATE_KEYWORDS_REGEX = "|".join(CANDIDATE_KEYWORDS)
    return CANDIDATE_KEYWORDS_REGEX


# Check if a keyword is in the text
def check_keywords_in_text(text):
    regex = get_candidate_keywords_regex()
    match = re.search(regex, text, re.IGNORECASE)
    if match:
        return True
    return False

# returns the 2nd level domain name www.southern.edu --> southern.edu
def get_domain_name(url):
    try:
        if not url:
            return url
        match = re.match("https?://(.*?)/.*", url, re.IGNORECASE)
        if not match:
            match = re.match("https?://(.*)",url,re.IGNORECASE)
        if not match:
            return None
        domain = match.group(1) # split on "." join the last two with a "." and you got it. 
        parts = domain.split(".")
        return ".".join(parts[-2:])
    except Exception as e:
        print(f"Failed in get_domain_name. Unable to find domainname in {url}. See: {str(e)}")
    return None

# Expects regular url of page -> url, domain name -> domain_name (e.g. scotnpatti.com)
def check_url_in_domain(url, domain_name):
    url_domain = get_domain_name(url)
    return url_domain == domain_name

# Used if we didn't find the LMS name in the home page
def evaluate_child_pages(anchors, driver, domain_url):
    urls = []
    domain_url = get_domain_name(domain_url)
    # choose URLs to evaluate
    for tag_text in anchors:
        if check_url_in_domain(anchors[tag_text], domain_url) and check_keywords_in_text(tag_text):
            urls.append(anchors[tag_text])
    print(f"   Checking {len(urls)} Child pages")
    # check those child pages we deem most likely to hold the LMS name
    pagecount = 1
    for url in urls:
        print(f"      {pagecount} - Sub-page: {url}")
        try: 
            driver.get(url)
            text = driver.page_source
            text = remove_style_elements(remove_scripts(text))
            keyword_dict, flag_found, lms_name = retrieve_keyword_dict(text)
            if flag_found:
                return keyword_dict, flag_found, url, lms_name
            sleep(randint(1,5))
        except Exception as e:
            print(f"        ... page error skipping sub-page {url} with error {str(e)}")
        pagecount += 1
    return {}, False, "None", "None"
    

# Evaluate a University to determine its LMS
def evaluate_university(url, driver):
    error = ""
    x = { "url" : url } # dictionary
    try: 
        driver.get(url)
        text = driver.page_source
        text = remove_style_elements(remove_scripts(text))
        x["keywords"], flag_found, lms_name = retrieve_keyword_dict(text) # checks for LMS name found and gives debug information in keywords dictionary.
    
        # OK we didn't find it and we'll have to look at second level pages. 
        if flag_found: 
            x["found_lms"] = True
            x["lms_name"] = lms_name
            x["data_found_url"] = url
            return x
        else:
            # we don't care about anchors unless we don't find it. and we don't need to save these!
            anchors = retrieve_anchor_dict(driver)
            keyword_dict, flag_found, sub_url, lms_name = evaluate_child_pages(anchors, driver, url)
            if flag_found:
                x["keywords"] = keyword_dict
                x["found_lms"] = True
                x["lms_name"] = lms_name
                x["data_found_url"] = sub_url
                return x
                # Sadly we didn't find it. Resort to not found case at end. 
    except Exception as e:
        error = f"   Skipping {url} - error ocurred accessing page: {str(e)}."
        print(error)
        
    x["found_lms"] = False 
    x["lms_name"] = "None"
    if error:
        x["data_found_url"] = "Error"
        x["error_data"] = error
    x["data_found_url"] = "None"  
    return x

# Loads a list of URLs to evaluate
def read_urls_from_file():
    global urlsQueue
    # read the batch.txt file. It should have a list of urls to analyze
    with open("batch.txt") as file:
        urlsQueue = [line.strip() for line in file]

# Main entry point for program
def main():
    read_urls_from_file() # stores urls in urlsQueue
    start_time =  time.time()
    last_time = start_time
    ### EDIT THIS FOR YOUR SYSTEM, YOUR chromedriver executable will LIKELY BE IN A DIFFERENT LOCATION
    DRIVER_PATH = r"C:\Program Files\Google\Chrome\chromedriver.exe"
    options = Options()
    options.headless = True
    options.add_argument("--window-size=1920,1200")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--log-level=3")
    options.accept_insecure_certs = True
    driver = webdriver.Chrome(options=options, executable_path=DRIVER_PATH)
    pageList = [] # This contains a results list with all the Universities that we evaluate.
    # Loop to find LMS type from each university homepage
    url_count = 0
    for url in urlsQueue:
        url_count += 1
        last_time = time.time()
        print(f"Starting: #{url_count} of {len(urlsQueue)} URLs: {url}")
        page = evaluate_university(url, driver)
        pageList.append(page)
        print(f"   URL: {url} took at {time.time() - last_time} seconds.")
    # Save the information back to a json file so we can evaluate it later
    jsonFile = open('results.json','w')
    jsonFile.write(json.dumps(pageList))
    jsonFile.close()
    driver.quit()
    end_time = time.time()
    diff = end_time - start_time
    print(f"Total Time = {diff} seconds.")



# -----------------------------------------------------------------------------
# Setup for execution & Execution

# Names we search for
LMS_NAMES = [
    "Canvas","Blackboard","Moodle","Sakai",
    "BrightSpace","D2L","Desire2Learn","Edmodo",
    "Skillsoft","Cornerstone","Schoology","NetDimensions",
    "Collaborize","Interactyx","Docebe","Meridian",
    "Lattidtude","Eduneering","Mzinga","Epsillen",
    "Inquisiq","SumTotal"
    ]

# Words searched for in anchor text of home page. 
CANDIDATE_KEYWORDS = [
    "online", "student", "resource", "edtech", "technology", "lms", "learning", "platform"
]

# This is generated from the CANDIDATE_KEYWORDS above. See: get_candidate_keywords_regex()
CANDIDATE_KEYWORDS_REGEX = ""

# This is now read from a file in main.
urlsQueue = []

if __name__ == "__main__":
    main()