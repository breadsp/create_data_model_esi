# -*- coding: utf-8 -*-
"""
Created on Tue Sep 16 09:11:25 2025

@author: breadsp2
"""
from langchain_core.prompts import PromptTemplate
import pandas as pd
import time
import re
import sys
from langchain_core.exceptions import OutputParserException
from langchain_neo4j import GraphCypherQAChain
from langchain_ollama import ChatOllama
from langchain_neo4j import Neo4jGraph
from langchain.callbacks.base import BaseCallbackHandler
from typing import Any #, Dict
from tabulate import tabulate
import streamlit as st
from streamlit_chat import message
from streamlit.components.v1 import html
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "aitestingdata2025"

# 1. Initialize your graph database connection
if "graph" not in st.session_state:
    st.session_state.graph = Neo4jGraph(
        url=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD
    )

if "driver" not in st.session_state:
    st.session_state.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD), encrypted=False)

st.set_page_config(
    page_title="PopSci AI Interface: Text to Cypher",
    layout="centered",
    initial_sidebar_state="expanded")

st.sidebar.header("Generated Cypher Query")
if "last_results" in st.session_state: 
    st.sidebar.code(st.session_state.last_results, language='cypher')

# load the training data which will be passed to the template
#train_df = pd.read_excel(r"/Users/davenportaw/Projects/create_data_model_esi/sample_queries.xlsx")
def contains_edit_keywords(cypher_query):
    edit_keywords = [
        "CREATE", "MERGE", "SET", "DELETE", "REMOVE",
        "CREATE INDEX", "DROP INDEX", "CREATE CONSTRAINT", "DROP CONSTRAINT", "FOREACH"
    ]
    # Check for each keyword (case-insensitive)
    for kw in edit_keywords:
        if re.search(kw, cypher_query, re.IGNORECASE):
        #if re.search(rf"\b{kw}\b", cypher_query, re.IGNORECASE):
            print(f"{kw} was found in the cypher query")
            return True
    return False

def convert_training_data(training_df):
    all_training_data = pd.DataFrame()
    for curr_dict in train_df:
        all_training_data = pd.concat([all_training_data, train_df[curr_dict]])
    
    all_training_data = all_training_data.drop_duplicates()
    all_training_data.reset_index(inplace=True, drop=True)
    return all_training_data

def create_examples_string(examples):
    examples_str = ""
    for row_idx in examples.index:
        examples_str += f"# {examples.loc[row_idx,'question']}\n{examples.loc[row_idx,'cypher']}\n\n"
    return examples_str

def display_error_line(ex):
    trace = []
    tb = ex.__traceback__
    while tb is not None:
        trace.append({"filename": tb.tb_frame.f_code.co_filename,
                      "name": tb.tb_frame.f_code.co_name,
                      "lineno": tb.tb_lineno})
        tb = tb.tb_next
    print(str({'type': type(ex).__name__, 'message': str(ex), 'trace': trace}))

if "cypher_examples_str" not in st.session_state:
    train_df = pd.read_excel(r"C:\Users\breadsp2\Desktop\olloma testing\sample_queries.xlsx", sheet_name=None)

    all_training_data = convert_training_data(train_df)
    st.session_state.cypher_examples_str = create_examples_string(all_training_data) 

################################################################################
# create the template that will be used by the model

custom_cypher_prompt_template = """
You are an expert Cypher developer. Your task is to generate a valid Cypher query for a graph database based on the user's question and the provided schema.

Do not use fields that contain original or unit as these are place holders and not data


It is NOT possible to access variables that are not declared in a WITH statement
DO NOT add variables that were not requested for example
APPLY all filtering prior to calling a WITH statement

If a variable is being counted, then ensure it is included in the return statement
Functions cannot be part of the where statement, use a with command 

Do not use ` in the cypher response
Do not use a count filter, if none was asked for
Do not include variables that were not implied in the users question
If age is being requested, then take age_at_entrolment / 365 for the filter criteria

DO NOT USE the function lower()
If a WITH statement is used the only variables in the WITH statement can be passed onto the WHERE and RETURN statements
Relationships can not be in a RETURN statment, they can only be used in a MERGE
COUNT can not be used in a WHERE statement, should only be used in a RETURN

Always use the tolower() function to ensure case-insensitive matching for string variables.
Always use the tofloat() for numeric variables.
Always use the contains() function to ensure correct matching with the exception of sex or gender.

Do not make nodes that do not exist in the supplied model, the cypher is restricted by nodes and variables that already exist

If multiple conditions are asked, then each gets its own filter
If a participant does not have cancer, then p.participant_case_indicator = "No"
When a specific cancer or cancers are included in the question, make sure they are also included as part of the cypher filtering

Do not force the cypher to fit the question, if a term was asked that does not exist then return "unable to answer your question"

Schema:
{schema}

Cypher examples:
{cypher_examples}

Question: {query}
Cypher query:
    
every cypher should have a participant count in the return statement
    
Do not include any explanations or apologies in your response. 
Respond with a Cypher statement only!
"""
#################################################################################
#Use contains(x) for the following variables: race, ethnicity, cancer_diagnosis_primary_site and cancer_diagnosis_disease_morphology 

prompt = PromptTemplate.from_template(custom_cypher_prompt_template)

# 2. Get the schema
schema = st.session_state.graph.get_schema

# remove variabes from the schema that serve as place holders and should not be used in any query
remove_list = ["type: STRING", "uuid: STRING", "study_id: FLOAT", "updated: DATE_TIME",
               "participant_id: STRING", "type: STRING", "uuid: STRING", "created: DATE_TIME", "age_at_first_cancer_diagnosis_original: FLOAT", 
               "age_at_enrollment_original: FLOAT", "age_at_first_cancer_diagnosis_original_unit: STRING", "age_at_enrollment_original_unit: STRING",
               "age_at_first_cancer_diagnosis_unit: STRING", "ncbi_taxonomy_id: INTEGER", "age_at_enrollment_unit: STRING"]

for i in remove_list:
    schema = schema.replace(i, "")
    
schema = schema.replace(", ,", ", ")

# 3. Create the full QA chain
if "chain" not in st.session_state:
    st.session_state.chain = GraphCypherQAChain.from_llm(
        llm = ChatOllama(temperature=0, model="llama3.2"),
        graph=st.session_state.graph,
        verbose=True,   #this prints the generated cypher, but does not save
        allow_dangerous_requests=True,
        cypher_prompt=prompt,
        validate_cypher=False,
        return_intermediate_steps=True,
        return_direct=True)

    st.session_state.chain.cypher_query_corrector = None

def correct_cypher(cypher_query):
    cypher_query = cypher_query.replace("participant_sex", "sex")
    cypher_query = cypher_query.replace("participant_race", "race")
    cypher_query = cypher_query.replace("participant_ethnicity", "ethnicity")
    return cypher_query

def smart_wrap_code(code):
    # Add a newline before Cypher keywords
    keywords = ["MATCH", "WHERE", "WITH", "RETURN", "ORDER BY", "LIMIT",","]
    for kw in keywords:
        code = re.sub(rf"\s*{kw}\s*", f"\n{kw} ", code)
    return code
# 4. Invoke the chain with few-shot examples
#query_list = ["how many particpants are in each study?", "how many studies have at least 5000 male participants",
#              "summerize participant counts by sex and race"]
#query_list = ["How many participants have kidney cancer?",
#              "List all ethnicities for each study",
#              "How many particpants are female, black and between 35 and 45 years old?"
#             ]

def get_query_data(tx, query):
    result = tx.run(query)
    data_list = [i for i in result.data()]
    return data_list

def update_side_bar(curr_query, cypher_query):
    #st.sidebar.header("Generated Cypher Query")
    wrapped_query = smart_wrap_code(cypher_query)
    if "last_query" not in st.session_state:
        st.session_state.last_query = [curr_query]
    else:
        st.session_state.last_query = st.session_state.last_query + [curr_query]
    
    if "last_code" not in st.session_state:
        st.session_state.last_code = [wrapped_query]
    else:
        st.session_state.last_code = st.session_state.last_code + [wrapped_query]
     
    for curr_idx in range(0,len(st.session_state.last_query)):   
        if len(st.session_state.last_query[curr_idx]) > 0:
            st.sidebar.text(f"Users Question: \n {st.session_state.last_query[curr_idx]}")
            st.sidebar.code(st.session_state.last_code[curr_idx], language='cypher')

if "repeat_loop" not in st.session_state:
    st.session_state.repeat_loop = True

# Define a style block to center the title
title_alignment = """
    <style>
    .centered-title {
        text-align: center;
    }
    </style>
"""
st.markdown(title_alignment, unsafe_allow_html=True)
st.markdown("<h1 class='centered-title'>PopSci AI: Query Database from User Input</h1>", unsafe_allow_html=True)

st.write("Welcome I am an AI program that can take a question, query my database and return an answer if applicable")
st.write("How can I help you today?")

def disable(status):
    st.session_state.input_disabled = status

if "input_disabled" not in st.session_state:
    st.session_state.input_disabled = False


if st.session_state.repeat_loop:
    curr_query = ""
    cypher_query = ""
    update_side_bar(curr_query, cypher_query)
    curr_query = st.text_input("User Input:", key="user_input", 
                               disabled=st.session_state.input_disabled)  

    if st.button("Submit Question", key= "sub_question", on_click=disable, args=(True,),
                 disabled=st.session_state.input_disabled):   #if clicked then disable input and button
        try:
            #print("User question:", curr_query)
            start_timer = time.perf_counter()
            with st.spinner("Generating response..."):
                # keeps trying to run the query, but if invaid will cause an error
                results = st.session_state.chain.invoke({"query": curr_query, "schema": schema,
                                                         "cypher_examples": st.session_state.cypher_examples_str})
                cypher_query = results['intermediate_steps'][0]['query']
                #print(cypher_query)
                if contains_edit_keywords(cypher_query):
                    cypher_query = "\nEdit keywords detected in Cypher query! Query will not be executed.\n"
                    #st.sidebar.warning("Edit keywords detected in Cypher query! Query will not be executed.")
                    st.write("Your query contains database editing commands and will not be run.")
                    print("Blocked query due to edit keywords:", cypher_query)
                    update_side_bar(curr_query, cypher_query)
                else:
                    cypher_query = correct_cypher(cypher_query)
                    update_side_bar(curr_query, cypher_query)

                    try:
                        #print("Raw results:", results)
                        with st.session_state.driver.session() as session:
                            records = session.execute_read(get_query_data, cypher_query)
                            result_df = pd.DataFrame(records)
                            result_df.drop_duplicates(inplace=True)
                            if len(result_df) > 0:
                                st.write(result_df)
                            else:
                                st.write("I was able to generate a valid cypher query")
                                st.write("However, I was not able to find any results that matched your question")
                    except Exception as e:
                        display_error_line(e)
                        st.write("Unfortunately the generated cypher query is not valid and I am not able to use it to answer your question")
                end_timer = time.perf_counter()
                st.write(f"Your question took {end_timer - start_timer:.2f} seconds to process \n")
        except Exception as e:
            display_error_line(e)
            # st.write("Exception:", e)
            st.write("I was unable to generate a valid cyper query based on your question")
            st.write("Please check for spelling or filtering criteria to ensure the question was asked correctly")
        # Ask if user wants to continue
        if st.button("Ask Another Question", on_click=disable, args=(False,)):
            #if user wants another question then enable input text and submit button
            st.session_state.user_input = ""  # Clear input for next question
            st.session_state.repeat_loop = True
    if st.button("End Session" , on_click=disable, args=(True,)):
        #user ended program, disable all buttons and inputs
        #print("Failed to click the button")
        st.session_state.repeat_loop = False
if st.session_state.repeat_loop == False:
    st.write("Thank you for using my program, hopefully I was able to answer all your questions")
    st.write("Goodbye...")
    st.stop()
    #print("thank you for using my program, hopefully I was able to answer all your questions")
    #print("Goodbye...")