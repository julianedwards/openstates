from openstates.utils import LXMLMixin
from pupa.scrape import Scraper, VoteEvent
from pupa.utils.generic import convert_pdf
import datetime
import subprocess
import lxml
import os
import re

journals = "http://www.leg.state.co.us/CLICS/CLICS%s/csljournals.nsf/" \
    "jouNav?Openform&%s"

date_re = re.compile(
    r"(?i).*(?P<dt>(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    ".*, \d{4}).*"
)
vote_re = re.compile((r"\s*"
           "YES\s*(?P<yes_count>\d+)\s*"
           "NO\s*(?P<no_count>\d+)\s*"
           "EXCUSED\s*(?P<excused_count>\d+)\s*"
           "ABSENT\s*(?P<abs_count>\d+).*"))
votes_re = r"(?P<name>\w+(\s\w\.)?)\s+(?P<vote>Y|N|A|E|-)"

class COVoteScraper(Scraper, LXMLMixin):

    def scrape_house(self, session):
        url = journals % (session, 'House')
        page = self.lxmlize(url)
        hrefs = page.xpath("//font//a")

        for href in hrefs:
            (path, response) = self.urlretrieve(href.attrib['href'])
            data = convert_pdf(path, type='text-nolayout').decode()

            in_vote = False
            cur_vote = {}
            known_date = None
            cur_vote_count = None
            in_question = False
            cur_question = None
            cur_bill_id = None

            for line in data.split("\n"):
                if known_date is None:
                     dt = date_re.findall(line)
                     if dt != []:
                        dt, dow = dt[0]
                        known_date = datetime.datetime.strptime(dt,
                            "%A, %B %d, %Y")

                non_std = False
                if re.match("(\s+)?\d+.*", line) is None:
                    non_std = True
                    l = line.lower().strip()
                    skip = False
                    blacklist = [
                        "house",
                        "page",
                        "general assembly",
                        "state of colorado",
                        "session",
                        "legislative day"
                    ]
                    for thing in blacklist:
                        if thing in l:
                            skip = True
                    if skip:
                        continue

                found = re.findall(
                    "(?P<bill_id>(H|S|SJ|HJ)(B|M|R)\d{2}-\d{3,4})",
                    line
                )
                if found != []:
                    found = found[0]
                    cur_bill_id, chamber, typ = found

                try:
                    print(non_std)
                    if not non_std:

                        print(line)
                        _, line = line.strip().split(" ", 1)
                        print(line+"**********************************************")
                    line = line.strip()
                except ValueError:
                    in_vote = False
                    in_question = False
                    continue

                if in_question:
                    cur_question += " " + line.strip()
                    continue

                if ("The question being" in line) or \
                   ("On motion of" in line) or \
                   ("the following" in line) or \
                   ("moved that the" in line):
                    cur_question = line.strip()
                    in_question = True

                print("Base-2")
                if in_vote:
                    print("base-1")
                    if line == "":
                        likely_garbage = True

                    likely_garbage = False
                    if "co-sponsor" in line.lower():
                        likely_garbage = True

                    if 'the speaker' in line.lower():
                        likely_garbage = True

                    votes = re.findall(votes_re, line)
                    if likely_garbage:
                        votes = []

                    for person, _, v in votes:
                        cur_vote[person] = v

                    last_line = False
                    for who, _, vote in votes:
                        if who.lower() == "speaker":
                            last_line = True     
                    if votes == [] or last_line:
                        in_vote = False
                        # save vote
                        yes, no, other = cur_vote_count
                        if cur_bill_id is None or cur_question is None:
                            continue

                        bc = {
                            "H": "lower",
                            "S": "upper",
                            "J": "joint"
                        }[cur_bill_id[0].upper()]
                        print("base0")
                        vote = Vote(chamber='lower',
                                    start_date=known_date,
                                    motion_text=cur_question,
                                    result = 'pass' if (yes > no) else 'fail',
                                    classification='passage',
                                    legislative_session=session,
                                    bill=cur_bill_id,
                                    bill_chamber=bc)

                        vote.add_source(href.attrib['href'])
                        vote.add_source(url)

                        for person in cur_vote:
                            if not person:
                                continue
                            vot = cur_vote[person]

                            if person.endswith("Y"):
                                vot = "Y"
                                person = person[:-1]
                            if person.endswith("N"):
                                vot = "N"
                                person = person[:-1]
                            if person.endswith("E"):
                                vot = "E"
                                person = person[:-1]

                            if not person:
                                continue

                            if vot == 'Y':
                                vote.yes(person)
                            elif vot == 'N':
                                vote.no(person)
                            elif vot == 'E':
                                vote.vote('excused', person)
                            elif vot == '-':
                                vote.vote('absent', person)

                    

                        cur_vote = {}
                        in_question = False
                        cur_question = None
                        in_vote = False
                        cur_vote_count = None
                        continue

                summ = vote_re.findall(line)
                if summ == []:
                    continue
                summ = summ[0]
                yes, no, exc, ab = summ
                yes, no, exc, ab = \
                        int(yes), int(no), int(exc), int(ab)
                vote.set_count('yes', yes)
                vote.set_count('no', no)
                vote.set_count('excused', exc)
                vote.set_count('absent', ab)
                other = exc + ab
                in_vote = True
                print("base2")
                yield vote
            os.unlink(path)

    def scrape_senate(self, session):
        url = journals % (session, 'Senate')
        page = self.lxmlize(url)
        hrefs = page.xpath("//font//a")
        for href in hrefs:
            (path, response) = self.urlretrieve(href.attrib['href'])
            data = convert_pdf(path, type='text-nolayout').decode()

            cur_bill_id = None
            cur_vote_count = None
            in_vote = False
            cur_question = None
            in_question = False
            known_date = None
            cur_vote = {}
            for line in data.split("\n"):
                if not known_date:
                    dt = date_re.findall(line)
                    if dt != []:
                        dt, dow = dt[0]
                        dt = dt.replace(',', '')
                        known_date = datetime.datetime.strptime(dt, "%A %B %d %Y")

                if in_question:
                    line = line.strip()
                    if re.match("\d+", line):
                        in_question = False
                        continue
                    try:
                        line, _ = line.rsplit(" ", 1)
                        cur_question += line.strip()
                    except ValueError:
                        in_question = False
                        continue

                    cur_question += line.strip()
                if not in_vote:
                    summ = vote_re.findall(line)
                    if summ != []:
                        cur_vote = {}
                        cur_vote_count = summ[0]
                        in_vote = True
                        continue

                    if ("The question being" in line) or \
                       ("On motion of" in line) or \
                       ("the following" in line) or \
                       ("moved that the" in line):
                        cur_question, _ = line.strip().rsplit(" ", 1)
                        cur_question = cur_question.strip()
                        in_question = True

                    if line.strip() == "":
                        continue
                    first = line[0]
                    if first != " ":
                        if " " not in line:
                            # wtf
                            continue

                        bill_id, kruft = line.split(" ", 1)
                        if len(bill_id) < 3:
                            continue
                        if bill_id[0] != "H" and bill_id[0] != "S":
                            continue
                        if bill_id[1] not in ['B', 'J', 'R', 'M']:
                            continue

                        cur_bill_id = bill_id
                else:
                    line = line.strip()
                    try:
                        line, lineno = line.rsplit(" ", 1)
                    except ValueError:
                        in_vote = False
                        if cur_question is None:
                            continue

                        if cur_bill_id is None:
                            continue

                        yes, no, exc, ab = cur_vote_count
                        other = int(exc) + int(ab)
                        exc = int(exc)
                        ab = int(ab)
                        yes, no, other = int(yes), int(no), int(other)

                        bc = {'H': 'lower', 'S': 'upper'}[cur_bill_id[0]]
                        vote = Vote(chamber='upper',
                                    start_date=known_date,
                                    motion_text=cur_question,
                                    result = 'pass' if (yes > no) else 'fail',
                                    classification='passage',
                                    legislative_session=session,
                                    bill=cur_bill_id,
                                    bill_chamber=bc)
                        for person in cur_vote:
                            if person is None:
                                continue

                            howvote = cur_vote[person]

                            if person.endswith("Y"):
                                howvote = "Y"
                                person = person[:-1]
                            if person.endswith("N"):
                                howvote = "N"
                                person = person[:-1]
                            if person.endswith("E"):
                                howvote = "E"
                                person = person[:-1]

                            howvote = howvote.upper()
                            if howvote == 'Y':
                                vote.yes(person)
                            elif howvote == 'N':
                                vote.no(person)
                            else:
                                vote.other(person)
                        vote.add_source(href.attrib['href'])
                        

                        cur_vote, cur_question, cur_vote_count = (
                            None, None, None)
                        yield vote
                        continue

                    votes = re.findall(votes_re, line)

                    for person in votes:
                        name, li, vot = person
                        cur_vote[name] = vot

            os.unlink(path)

    def scrape(self, chamber=None, session=None):
        if not session:
            session = self.latest_session()
            self.info('no session specified, using %s', session)
        if chamber == 'upper':
            yield from self.scrape_senate(session)
        elif chamber == 'lower':
            yield from self.scrape_house(session)
        else:
            yield from self.scrape_house(session)
            #yield from self.scrape_senate(session)
