from browser.browser_helpers import *
from download.download_monitor import *


def extract_doc_url(element, base_url="https://ccms.clerk.org/viewDocument.aspx?v1="):
    """
    Extract document ID from onclick attribute and build download URL

    Args:
        element: Selenium WebElement with onclick attribute
        base_url: Base URL template for document viewing

    Returns:
        str: Complete document URL or None if extraction fails
    """
    try:
        # Get onclick attribute
        onclick = element.get_attribute('onclick')
        print(f"onclick : {onclick}")
        # Extract doc ID using regex
        # Pattern: viewDocNoQueryString('DOCID','','', this);return false;
        match = re.search(r"viewDocNoQueryString\('([^']+)'", onclick)
        match2 = re.search(r"viewDialog\('([^']+)'", onclick)

        if match:
            doc_id = match.group(1)
            full_url = f"{base_url}{doc_id}"
            print(f"✅ Extracted doc ID: {doc_id}")
            print(f"✅ Built URL: {full_url}")
            return full_url
        else:
            if match2:
                doc_id = match2.group(1)
                full_url = f"{base_url}{doc_id}"
                print(f"✅ Extracted doc ID: {doc_id}")
                print(f"✅ Built URL: {full_url}")
                return full_url
            else:
                print(f"❌ Could not extract doc ID from: {onclick}")
                return None

    except Exception as e:
        print(f"❌ Error extracting doc ID: ")
        traceback.print_exc()
        return None




def navigate_to_url_vs(driver,case_id):
    request_url(driver, "https://ccms.clerk.org")


def navigate_to_files_table_vs(driver):
    try:
        portential_error = driver.find_element('xpath', '//*[@id="DivMain"]/div[2]/table/tbody/tr/td/div/div[1]/div')
        if "request" in portential_error.text.lower():
            return 1
        case1 = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, 'CaseNum'))
        )
        driver.get(case1.get_attribute('href'))

        wait_and_click(driver, By.ID, '__tab_docket')

    except:
        if element_exists_id(driver,'Label2'):
            return 2



def trigger_download_vs(driver,docket_eg,row_index,download_mgr,before_files,matching_row=None):
    driver.switch_to_window(driver.window_handles[0])
    docket_eg_button = docket_eg.find_element(By.ID, 'selectVB')
    print(f"docket_eg_button : {docket_eg_button.get_attribute('onclick')}")
    attempt=0
    while attempt<5:
        set_download_dir(driver,download_mgr.download_dir)
        switch_to_window_by_url_prefix(driver, "https://ccms.clerk.org/caseCM")
        driver.execute_script("arguments[0].scrollIntoView();", docket_eg_button)
        doc_url = extract_doc_url(docket_eg_button)
        down_flag=None
        while not down_flag:
            set_download_dir(driver,download_mgr.download_dir)
            if doc_url:
                create_new_tab(driver)
                request_url(driver,doc_url)
                down_flag = download_mgr.wait_for_download_start(before_files)
            else:
                return 1
        switch_to_window_by_url_prefix(driver,"https://ccms.clerk.org/viewDocument.aspx")
        driver.close()
        return
    switch_to_window_by_url_prefix(driver, "https://ccms.clerk.org/viewDocument.aspx")




def navigate_to_search_vs(driver):


    if element_exists_xpath(driver,'//*[@id="DivMain"]/div[2]/table/tbody/tr/td/div'):
        if "critical error" in driver.find_element('xpath','//*[@id="DivMain"]/div[2]/table/tbody/tr/td/div').text.lower():
            return 1
    wait_and_click(driver, By.ID, 'Content1_button_accept')
    WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.ID, 'Content1_CaseNum'))
    )


def search_case_number_vs(driver, case_number):
    input_case = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.ID, 'Content1_CaseNum'))
    )
    input_case.send_keys(case_number)
    wait_and_click(driver, By.ID, 'Content1_lb_submit')


def show_parties_vs(driver):
    wait_and_click(driver, By.ID, '__tab_parties')


def show_dockets_vs(driver):
    wait_and_click(driver, By.ID, '__tab_docket')
