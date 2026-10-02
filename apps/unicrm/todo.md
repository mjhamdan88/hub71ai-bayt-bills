# Email marketing finalization

[X]: Add a unibot find_staff_email tool that takes company domain name or names and contact full name and does some trial and error with ReacherHQ to find their email
[ ]: Add a unibot tool, find_contacts, which searches the web with chatGPT for names of staff members of specific roles, and then uses find_staff_email to find the contact info of these staff members
[ ]: Add a unibot tool, find_b2b_leads which takes specific definitions and criteria for precisely targeting b2b leads, and it does some each using a mix of chatGPT search and google maps API, and once it collects a list of companies and decides the roles to be contacted for each company, it calls find_contacts on each to find their contact info and finalize the data.
[ ]: Use "Django Data Wizard" or other tools for imports and exports, or even possibly LLMs https://chatgpt.com/share/69088d31-dd24-800e-9025-805ca368bdcd





# To solve a few issues and clean some technical debt
[ ]: CommunicaitonMessage objects are being created as soon as the Communication object is created. This is very wrong design and they're supposed to only be created as soon as the unicom Message objects are sent, and the CommunicaitonMessage.message field should not be nullable
