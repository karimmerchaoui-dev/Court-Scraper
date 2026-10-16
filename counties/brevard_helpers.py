from browser.browser_helpers import *
from download.download_monitor import *


def search_case_number_brevard(driver, case):


    if element_exists_id(driver,'content') and "denied" in driver.find_element(By.ID,'content'):
        return 1
    #Split the case number into 6
    case_chunks = case.split('-')

    #Enter each part of the case number in it's correct place
    ci1 = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/form/div[1]/input[1]'))
    )
    ci1.send_keys(case_chunks[0])
    WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/form/div[1]/input[2]'))
    ).send_keys(case_chunks[1])
    WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/form/div[1]/input[3]'))
    ).send_keys(case_chunks[2])
    WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/form/div[1]/input[4]'))
    ).send_keys(case_chunks[3])

    driver.find_element("xpath", "/html/body/form/div[3]/input[1]").click()
    #
    try:#
        invalid_case = WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.XPATH, '/html/body/div[4]/h4'))
        )
        if "Invalid Case Number" in invalid_case.text:
            return 2
        if "A Case Number Must" in invalid_case.text:
            return search_case_number_brevard(driver, case)
    except TimeoutException:
        pass


def navigate_to_search_brevard(driver):
    try:
        first_element = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, '/html/body/form/table/tbody/tr[2]/td/center/input'))
        )
    except TimeoutException:
        return
    first_element.click()

    # Wait for "General public search" button to appear (indicates page reload)
    try:
        wait_and_click(driver, By.XPATH, "/html/body/div[3]/button[1]")
    except TimeoutException:
        #If it fails to load, the page gets reloaded
        if element_exists_xpath(driver, '//*[@id="content"]/div/fieldset/h2'):
            driver.refresh()
            return navigate_to_search_brevard(driver)

    # Click on "Case Number" Button

    #wait_and_click(driver, By.XPATH, '/html/body/div[2]/button[1]')
    wait_and_click(driver, By.XPATH, '//*[@id="csnbr"]/a')

def navigate_to_files_table_brevard(driver):
    pass

def navigate_to_url_brevard(driver,case_id):
    request_url(driver,"https://vmatrix1.brevardclerk.us/beca/CaseNumber_Search.cfm")




def trigger_download_brevard(driver,docket_eg,row_index,download_mgr,before_files,matching_row=None):
    href = matching_row.get('href')
    if not href:
        return 2
    down_flag=None
    attempt = 0
    while attempt < 3 and not down_flag:
        set_download_dir(driver, download_mgr.download_dir)
        if href:
            driver.switch_to.window(driver.window_handles[0])
            if not element_exists_xpath(driver,f'//*[@id="tbl-content"]/tbody/tr[{row_index}]/td[1]/a'):
                return 2
            button=docket_eg.find_element(By.XPATH,f'//*[@id="tbl-content"]/tbody/tr[{row_index}]/td[1]/a')
            if button.get_attribute('title') =="View On Request":
                return 2
            button.click()
            down_flag = download_mgr.wait_for_download_start(before_files)

        else:
            return 1
        open_downloads_tab(driver)