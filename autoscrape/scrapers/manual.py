# -*- coding: UTF-8 -*-
import time
import hashlib
import logging
import os
import string
import sys
import re
from itertools import product

from . import BaseScraper
from ..control import Controller


logger = logging.getLogger('AUTOSCRAPE')


class ManualControlScraper(BaseScraper):
    """
    A Depth-First Search scraper that looks for forms, inputs, and next
    buttons by some manual criteria and iterates accordingly.
    """

    # TODO: save the path to the matched search form to a file. then
    # upon subsequent loads, we can try that path first and then go
    # from there. this way the manual control scraper can learn from
    # self-exploration based on manual params
    #
    # Another related idea: it would be nice if we had an API that
    # saved data about successful runs and loading/replaying them
    # so users can get familiar with the concepts of self-exploration
    # and self-learning but without having to get the ML concepts.

    def __init__(self, baseurl, maxdepth=10, loglevel=None, formdepth=0,
                 next_match="next page", form_match="first name",
                 output_data_dir=None, input_type="character_iteration",
                 input_strings="", input_minlength=1, wildcard=None,
                 form_input_range=None, leave_host=False, driver="Firefox",
                 link_priority="search", form_submit_natural_click=False,
                 form_input_index=0, form_submit_wait=5, load_images=False,
                 headless=True):
        # setup logging, etc
        super(ManualControlScraper, self).setup_logging(loglevel=loglevel)
        # set up web scraper controller
        self.control = Controller(
            leave_host=leave_host, driver=driver,
            form_submit_natural_click=form_submit_natural_click,
            form_submit_wait=form_submit_wait,
            load_images=load_images, headless=headless,
        )
        self.control.initialize(baseurl)
        # depth of DFS in search of form
        self.maxdepth = maxdepth
        # current depth of iterating through 'next' form buttons
        self.formdepth = formdepth
        # match for link to identify a "next" button
        self.next_match = next_match
        # string to match a form (by element text) we want to scrape
        self.form_match = form_match
        # Where to write training data from crawl
        self.output_data_dir = output_data_dir
        # minimum length of form inputs (in characters)
        self.input_minlength = input_minlength
        # Additonal filter for range of chars inputted to forms as search
        self.form_input_range = form_input_range
        # Wildcard character to be added to search inputs
        self.wildcard = wildcard
        # string used to match link text in order to sort them higher
        self.link_priority = link_priority
        # attempt a position-based "natural click" over the element
        self.form_submit_natural_click = form_submit_natural_click
        # a period of seconds to force a wait after a submit
        self.form_submit_wait = form_submit_wait
        # which input to target
        self.form_input_index = form_input_index
        # how to interact with inputs
        self.input_type = input_type
        # list of comma separated strings to use with fixed_strings mode
        self.input_strings = input_strings

    def save_screenshot(self):
        t = int(time.time())
        screenshot_dir = os.path.join(self.output_data_dir, "screenshots")
        if not os.path.exists(screenshot_dir):
            os.mkdir(screenshot_dir)
        filepath = os.path.join(screenshot_dir, "%s.png" % t)
        logger.debug("Saving screenshot to file: %s." % filepath);
        with open(filepath, "wb") as f:
            png = self.control.scraper.driver.get_screenshot_as_png()
            f.write(png)

    def save_training_page(self, classname=None):
        """
        Writes the current page to the output data directory (if provided)
        to the given class folder.
        """
        logger.debug("Saving training page for class: %s" % classname)
        classes = [
            "data_pages", "error_pages", "links_to_documents",
            "links_to_search", "search_pages"
        ]
        if classname not in classes:
            raise ValueError("Base class speficied: %s" % classname)

        if not self.output_data_dir:
            return

        classdir = os.path.join(self.output_data_dir, classname)
        if not os.path.exists(classdir):
            os.mkdir(classdir)

        html = self.control.scraper.page_html
        url = self.control.scraper.page_url
        h = hashlib.sha256(html.encode("utf-8")).digest().hex()
        logger.debug("URL: %s, Hash: %s" % (url, h))
        filepath = os.path.join(classdir, "%s.html" % h)

        with open(filepath, "w") as f:
            f.write(html)

    def character_iteration_input_generator(self, length=1):
        chars = string.ascii_lowercase
        if self.form_input_range:
            chars = self.form_input_range

        for input in product(chars, repeat=length):

            inp = "".join(input)
            if self.wildcard:
                inp += self.wildcard

            yield [{
                "index": self.form_input_index,
                "string": inp,
            }]

    def make_input_generator(self):
        """
        Make a form input generator by parsing our kwargs. Output
        is a multidimensional array, where the first dimension is
        independent searches to attempt and the second dimension is
        which inputs for fill. Example:

            [
              [
                { "index": 0, "string": "test%" }
              ],
              [
                { "index": 0, "string": "test%" },
                { "index": 1, "string": "form%" },
              ],
            ]

        This will try two independent searches w/ form iterations,
        the first time it will fill input 0 with "test%" and the second
        time it will fill inputs 0 and 1 with strings "test%" and
        "form%", respectively.
        """
        logger.debug("Input strategy: %s" % self.input_type)
        input_gen = []
        if self.input_type == "character_iteration":
            indiv_search_gen = self.character_iteration_input_generator(
                length=self.input_minlength
            )
            for indiv_search in indiv_search_gen:
                yield indiv_search

        elif self.input_type == "fixed_strings" and self.input_strings:
            indiv_searches = re.split(r'(?<!\\),', self.input_strings)
            logger.debug("Manual input strings: %s" % input_gen)
            for indiv_search in indiv_searches:
                yield [{
                    "index": self.form_input_index,
                    "string": indiv_search,
                }]

        # This format is the following:
        # 0:firstinput,1:secondinput;0:another,1:another2
        elif self.input_type == "multi_manual" and self.input_strings:
            # split the independent searches first
            inputs = re.split(r'(?<!\\);', self.input_strings)
            for inp in inputs:
                indiv_search = []
                # split the inputs to be filled per search
                indiv_inputs_list = re.split(r'(?<!\\),', inp)
                for indiv_inputs in indiv_inputs_list:
                    ix, string = indiv_inputs.split(":", 1)
                    indiv_search.append({
                        "index": int(ix),
                        "string": string.replace("\,", ",").replace("\;", ";"),
                    })

                yield indiv_search

        # bad combination of options. TODO: we need to make the
        # cli parser validate this better. maybe when we move to
        # click or some other library
        else:
            raise Exception("Invalid input type combination supplied!")

    def keep_clicking_next_btns(self, maxdepth=0):
        """
        This looks for "next" buttons, or (in the future) page number
        links, and clicks them until one is not found. This saves the
        pages as it goes.
        """
        logger.debug("*** Entering 'next' iteration routine")
        depth = 0
        while True:
            if self.formdepth and depth > self.formdepth:
                logger.debug("Max 'next' formdepth reached %s" % depth)
                break

            found_next = False
            button_data = self.control.button_vectors()
            n_buttons = len(button_data)
            logger.debug("** 'Next' Iteration Depth %s" % depth)
            logger.debug("Button vectors (%s): %s" % (
                n_buttons, button_data))

            # save the initial landing data page
            self.save_training_page(classname="data_pages")
            self.save_screenshot()

            for ix in range(n_buttons):
                button = button_data[ix]
                # TODO: replace this with a ML model to decide whether or
                # not this is a "next" button.
                logger.debug("Checking button: %s" % button)
                if self.next_match.lower() in button.lower():
                    logger.debug("Next button found! Clicking: %s" % ix)
                    depth += 1
                    self.control.select_button(ix, iterating_form=True)
                    # subsequent page loads get saved here
                    self.save_training_page(classname="data_pages")
                    self.save_screenshot()

                    found_next = True
                    # don't click any other next buttons
                    break

            if not found_next:
                logger.debug("Next button not found!")
                break

        for _ in range(depth):
            logger.debug("Going back from 'next'...")
            self.control.back()

    def run(self, depth=0):
        logger.debug("** Crawl depth %s" % depth)
        if depth > self.maxdepth:
            logger.debug("Maximum depth %s reached, returning..." % depth)
            self.control.back()
            return

        self.save_screenshot()
        scraped = False
        form_vectors = self.control.form_vectors(type="text")

        for ix in range(len(form_vectors)):
            form_data = form_vectors[ix]
            # inputs are keyed by form index
            inputs = self.control.inputs[ix]

            logger.debug("Form: %s Text: %s" % (ix, form_data))
            logger.debug("Inputs: %s" % inputs)

            # TODO: ML model here to determine if this form is
            # scrapeable. Currently this uses strict text match.
            if self.form_match.lower() not in form_data.lower():
                continue

            logger.debug("*** Found an input form!")
            self.save_training_page(classname="search_pages")
            self.save_screenshot()

            input_gen = self.make_input_generator()

            # TODO: ML model here to determine which inputs require
            # input before submission. The form-selecting classifier
            # above has already made the decision to submit this form,
            # so that is assumed at this point.
            for input_phase in input_gen:
                logger.debug("Input plan: %s" % input_phase)
                for single_input in input_phase:
                    input_index = single_input["index"]
                    input_string = single_input["string"]
                    logger.debug("Inputting %s to input %s" % (
                        input_string, input_index))
                    self.control.input(ix, input_index, input_string)
                self.save_screenshot()
                self.control.submit(ix)
                logger.debug("Beginning iteration of data pages")
                self.save_screenshot()
                self.keep_clicking_next_btns(maxdepth=3)
                scraped = True
                self.control.back()

            logger.debug("Completed iteration!")
            # Only scrape a single form, due to explicit, single
            # match configuration option

            if scraped:
                logger.debug("Scrape complete! Exiting.")
                sys.exit(0)

        # TODO: this will be replaced by a ML algorith to sort links by those
        # most likely to be fruitful
        links = self.control.clickable
        link_vectors = self.control.link_vectors()
        link_zip = list(zip(range(len(link_vectors)),link_vectors))
        link_zip.sort(
            key=lambda r: self.link_priority in r[1].lower(),
            reverse=True
        )
        for ix, _ in link_zip:
            if depth == self.maxdepth:
                logger.debug("At maximum depth: %s, skipping links." % depth)
                break

            if self.control.select_link(ix):
                logger.debug("Clicked! Recursing ...")
                self.run(depth=depth + 1)

        logger.debug("Searching forms and links on page complete")
        self.control.back()

