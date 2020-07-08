#!/usr/bin/env python3
from argparse import ArgumentParser, RawTextHelpFormatter
from os import linesep
from os.path import exists
from random import choice
from time import sleep

from bs4 import BeautifulSoup as bs
from linkedin_scraper import actions
from selenium import webdriver

DEFAULT_SEARCH_LIMIT = 200
DEFAULT_VISITED_PROFILES_FILE = 'visited.txt'
DEFAULT_OUTPUT_FILE = 'linked-loot.txt'


def get_arguments():
    parser = ArgumentParser(formatter_class=RawTextHelpFormatter)
    parser.add_argument('--login',
                        dest='login',
                        required=False,
                        type=str,
                        help='Specify your linkedin login email.')
    parser.add_argument('--password',
                        dest='password',
                        required=False,
                        type=str,
                        help='Specify your linkedin login password.')
    parser.add_argument('--credentials-file',
                        dest='credentials_file',
                        required=False,
                        type=str,
                        help='Specify a file name with new-line separated credentials to use. '
                             'Should be in the following format: '
                             'login=your@email.com'
                             f'{linesep}'
                             'password=yourSuperSecretPassword')
    parser.add_argument('--search',
                        dest='search',
                        required=False,
                        type=str,
                        help='Specify a keyword to search for -  a job title, for example. '
                             'The script then collects links to the found persons in a txt file.')
    parser.add_argument('--search-limit',
                        dest='search_limit',
                        required=False,
                        default=DEFAULT_SEARCH_LIMIT,
                        type=int,
                        help='Specify a number of pages to collect. '
                             f'Default is {DEFAULT_SEARCH_LIMIT} '
                             'which basically means collecting of all the possible entries.')
    parser.add_argument('--connect',
                        dest='connect',
                        required=False,
                        type=str,
                        help='Specify a name to the file with a new-line separated list of URLs of people to connect with.')
    parser.add_argument('--visited-profiles',
                        dest='visited_profiles',
                        required=False,
                        default=DEFAULT_VISITED_PROFILES_FILE,
                        type=str,
                        help='Specify a name to the file with a new-line separated list of visited URLs. '
                             f'Default is {DEFAULT_VISITED_PROFILES_FILE}')
    parser.add_argument('--output',
                        dest='output',
                        required=False,
                        default=DEFAULT_OUTPUT_FILE,
                        type=str,
                        help='Specify a name for the output file to write the results to. '
                             f'Default is {DEFAULT_OUTPUT_FILE}')
    options = parser.parse_args()
    if options.login and options.password and options.credentials_file:
        parser.error('You must specify either a file with credentials or provide --login and --password arguments. '
                     'Use --help for more info.')
    if not options.credentials_file:
        if not options.login or not options.password:
            parser.error('One of the mandatory arguments is missing: --login or --password')
    else:
        with open(options.credentials_file, 'r', encoding='utf-8') as f:
            creds = [line.strip() for line in f.readlines() if line.strip()]
            options.login = creds[0].split('=')[1]
            options.password = creds[1].split('=')[1]
    return options


class LinkedinCrawler:
    def __init__(self, driver, visited_profiles_file):
        self.driver = driver
        self.visited_profiles_file = visited_profiles_file

    def authenticate(self, login, password):
        print('Logging in')
        actions.login(self.driver, login, password)
        print('Crawler has logged in')

    def get(self, url):
        self.driver.get(url)

    def page_source(self):
        return self.driver.page_source

    def collect_links_from_page(self, page_url):
        self.get(page_url)
        print(f'The search page {page_url} has been opened')
        self.driver.execute_script('window.scrollTo(0, 1000000)')
        print('Collecting links to people from the page')
        soup = bs(self.page_source(), 'html.parser')
        links = set()
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith('/in'):
                links.add(f'https://www.linkedin.com{href}')
        print(f'{len(links)} links have been scraped')
        return links

    def has_next_search_page(self):
        soup = bs(self.page_source(), 'html.parser')
        for tag in soup.find_all('span'):
            if 'next' in tag.text.lower():
                if tag.attrs['class'][0] == 'artdeco-button__text':
                    return True

    def get_current_page_number(self):
        soup = bs(self.page_source(), 'html.parser')
        for tag in soup.find_all('button'):
            if 'current page' in tag.text.lower():
                return int(tag.text.strip().split(linesep)[0])

    def connect(self, person_url):
        if self.is_profile_visited(person_url):
            return
        self.get(person_url)

        self.mark_profile_as_visited(person_url)
        try:
            all_buttons = self.driver.find_elements_by_tag_name('button')
            for button in all_buttons:
                if 'connect' in button.text.lower():
                    button.click()
                    print('The invitation has been sent')
                    return True
        except Exception as e:
            print(f"Couldn't send the invitation: {e}")

    def mark_profile_as_visited(self, person_url):
        if not self.is_profile_visited(person_url):
            with open(self.visited_profiles_file, 'a', encoding='utf-8') as f:
                f.write(person_url)
                f.write(linesep)

    def is_profile_visited(self, person_url):
        if exists(self.visited_profiles_file):
            with open(self.visited_profiles_file, 'r', encoding='utf-8') as f:
                visited_profiles = [line.strip() for line in f.readlines() if line.strip()]
            for profile_url in visited_profiles:
                if person_url.lower() in profile_url:
                    print(f'{person_url} has been already visited.')
                    return True

    def store(self, links, output_file):
        with open(output_file, 'a', encoding='utf-8') as f:
            for link in links:
                f.write(link)
                f.write(linesep)


def collect_links_to_people(driver, search_keyword, page_limit, output_file):
    print(f"Visiting the search page for {search_keyword}")
    search_url = f'https://www.linkedin.com/search/results/all/?keywords={search_keyword.replace(" ", "+")}' \
                 f'&origin=GLOBAL_SEARCH_HEADER'
    links_from_first_page = driver.collect_links_from_page(search_url)
    if links_from_first_page:
        driver.store(links_from_first_page, output_file)

    while driver.has_next_search_page():
        current_page_number = driver.get_current_page_number()
        if current_page_number > page_limit:
            break
        else:
            new_url = f'{search_url}&page={current_page_number + 1}'
            new_links = driver.collect_links_from_page(new_url)
            if new_links:
                driver.store(new_links, output_file)


options = get_arguments()

driver = LinkedinCrawler(driver=webdriver.Chrome(),
                         visited_profiles_file=options.visited_profiles)
driver.authenticate(login=options.login, password=options.password)

if options.search:
    collect_links_to_people(driver=driver,
                            search_keyword=options.search,
                            page_limit=options.search_limit,
                            output_file=options.output)
if options.connect:
    with open(options.connect, 'r', encoding='utf-8') as f:
        people_url_list = [line.strip() for line in f.readlines() if line.strip()]
        connected_persons = 0
        for i, person_url in enumerate(people_url_list):
            sleep(choice(range(1, 3)))
            print(f'[{i + 1}/{len(people_url_list)}] Connecting with {person_url}')
            is_connected = driver.connect(person_url)
            if is_connected:
                connected_persons += 1
        print(f'The crawler has successfully connected with {connected_persons} persons')
