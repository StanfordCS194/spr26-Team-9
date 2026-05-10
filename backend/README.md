## `backend/`

Handles user searches for news stories. Also stores data for user profiles including past searches and a variety of KPIs.

## Search

Handles two search targets:
- Local articles stored as json in `../data/`
- API to Google Big Query, specifically the GDELT Event Database

Search entrypoint is an API. Accessed by the frontend via a search bar (TO BE IMPLEMENTED. FOR PROTTYPING JUST HARDCODE SOME SEARCH TERMS AND/OR MAKE A DUMMY REQUEST FROM THE FRONTEND). 

#### Local article search

- Method: Natural language keyword matching algorithm. (Suggestions needed).
- Details: Local article json files are quite small and are refreshed every day. There should be some measurable confidence rating for matched articles.

#### API to Google Big Query

- Method: API call. (Need to look into the specifics. Suggestions are encouraged).
- Details: TO BE IMPLEMENTED. FOR PROTOTYPING JUST FOCUS ON LOCAL SEARCH FOR NOW.

## User Profile Data

Store a history of all user's searches and KPIs. Data store method is unknown, perhaps Redis for prototype.

#### KPIs

- Session duration.
- Percentage of users who return to the platform at least once within a week of use. Also track the number of returns per week.
- Number of searches per week.
- Articles viewed per session.
- Percentage of sessions where users utilize the comparison feature. Number of times the comparison function is utilized in a session.
- Percentage of sessions where users run at least one LLM bias analysis.

## Notes
Some frontend components are not built yet like the search bar or creating user profile page.