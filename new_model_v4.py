# -*- coding: utf-8 -*-
"""
Created on Tue Sep 16 09:11:25 2025

@author: breadsp2
"""

from langchain_core.prompts import PromptTemplate
import pandas as pd
import time
from tabulate import tabulate

# load the training data which will be passed to the template
train_df = pd.read_excel("sample_queries.xlsx")

def create_examples_string(examples):
    examples_str = ""
    for row_idx in examples.index:
        examples_str += f"# {examples.loc[row_idx,'question']}\n{examples.loc[row_idx,'cypher']}\n\n"
    return examples_str

cypher_examples_str = create_examples_string(train_df)    

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

Question: {question}
Cypher query:
    
every cypher should have a participant count in the return statement
    
Do not include any explanations or apologies in your response. 
Respond with a Cypher statement only!


Do not include any explanations or apologies in your response. 
Respond with a Cypher statement only!
"""
#################################################################################
#Use contains(x) for the following variables: race, ethnicity, cancer_diagnosis_primary_site and cancer_diagnosis_disease_morphology 

prompt = PromptTemplate.from_template(custom_cypher_prompt_template)


from langchain_community.graphs import Neo4jGraph
from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
from langchain_ollama import ChatOllama

# 1. Initialize your graph database connection
graph = Neo4jGraph(url="neo4j://127.0.0.1:7687", username="neo4j", password="SubmitterData2025!")

# 2. Get the schema
schema = graph.get_schema

# remove variabes from the schema that serve as place holders and should not be used in any query
remove_list = ["type: STRING", "uuid: STRING", "study_id: FLOAT", "updated: DATE_TIME",
               "participant_id: STRING", "type: STRING", "uuid: STRING", "created: DATE_TIME", "age_at_first_cancer_diagnosis_original: FLOAT", 
               "age_at_enrollment_original: FLOAT", "age_at_first_cancer_diagnosis_original_unit: STRING", "age_at_enrollment_original_unit: STRING",
               "age_at_first_cancer_diagnosis_unit: STRING", "ncbi_taxonomy_id: INTEGER", "age_at_enrollment_unit: STRING"]

for i in remove_list:
    schema = schema.replace(i, "")
    
schema = schema.replace(", ,", ", ")

# 3. Create the full QA chain
chain = GraphCypherQAChain.from_llm(
    llm = ChatOllama(temperature=0, model="llama3.2"),
    graph=graph,
    verbose=False,
    allow_dangerous_requests=True,
    cypher_prompt=prompt,
    validate_cypher=True,
    return_intermediate_steps=True,
    return_direct=True,
    input_key="question")


# 4. Invoke the chain with few-shot examples
#query_list = ["how many particpants are in each study?", "how many studies have at least 5000 male participants",
#              "summerize participant counts by sex and race"]
#query_list = ["How many participants have kidney cancer?",
#              "List all ethnicities for each study",
#              "How many particpants are female, black and between 35 and 45 years old?"
#             ]


repeat_loop = True

if repeat_loop:
    try:
        print('\x0c')
        print("Welcome I am an AI program that can take a question, query my database and return an answer if applicable")
        curr_query = input('How can I help you today? \n')
        start_timer = time.perf_counter()
        results = chain.invoke({"question": curr_query, "schema": schema, "cypher_examples": cypher_examples_str})
        print("\n\n")

        print("Here is a summary: \n")
        
        result_df = pd.DataFrame(results["result"])
        result_df.drop_duplicates(inplace=True)    
        print(f"the question that was asked:\n{results['question']}\n")
        print(f"The Generated Cypher Response:\n{results['intermediate_steps'][0]['query']}\n")
        
        if len(result_df) > 0:
            print("Tabulated output for the results of the cypher response")
            print(tabulate(result_df, headers='keys', tablefmt="rounded_grid", maxcolwidths=30))
        else:
            print("I was able to create a cypher query based on your question")
            print("Unfortunately it returned 0 results")
        
        end_timer = time.perf_counter()
        print(f"Your question took {end_timer - start_timer:.2f} seconds to process \n")
    except Exception:
        print("I was unable to generate a valid cyper query based on your question")
        print("Please check for spelling or filtering criteria to ensure the question was asked correctly")
    finally:
        answer = input("\nWould you like to ask another question?")
        if answer.lower() == 'yes':
            repeat_loop = True
        else:
            repeat_loop = False

print("thank you for using my program, hopefully I was able to answer all your questions")
print("Goodbye...")