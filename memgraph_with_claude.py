# -*- coding: utf-8 -*-
"""
Created on Fri Feb 20 09:12:54 2026

@author: breadsp2
"""

def display_error_line(ex):
    trace = []
    tb = ex.__traceback__
    while tb is not None:
        trace.append({"filename": tb.tb_frame.f_code.co_filename,
                      "name": tb.tb_frame.f_code.co_name,
                      "lineno": tb.tb_lineno})
        tb = tb.tb_next
    print(str({'type': type(ex).__name__, 'message': str(ex), 'trace': trace}))

import os
from langchain_anthropic import ChatAnthropic

# Initialize Anthropic client
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
model = ChatAnthropic(model="claude-haiku-4-5-20251001", api_key=ANTHROPIC_API_KEY )


## load all necessary librarys to run this agent 
from langchain_memgraph.toolkits import MemgraphToolkit
import mgclient
from langchain_memgraph.graphs.memgraph import MemgraphLangChain
from langchain_classic.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

## create a class that has the memgraph connection 
class Memgraph_DB():
    def __init__(self):
        self.host = "127.0.0.1"
        self.port =  7687
        self.username = ""
        self.password = ""
        
        self.conn = mgclient.connect(host=self.host, port=self.port) #, username=self.username, password=self.password)
        self.cursor = self.conn.cursor()

MEM_DB = Memgraph_DB()
memgraph_url = f"bolt://localhost:{MEM_DB.port}"

db = MemgraphLangChain(url=memgraph_url, username=MEM_DB.username, password=MEM_DB.password)
print("Connected to Memgraph")

## get the toolkits from memgraph that will be used
toolkit = MemgraphToolkit(db=db, llm=model)
tools = toolkit.get_tools()
tools = [tool for tool in tools if tool.name not in ["run_cypher"]]

tool_names = [tool.name for tool in tools]
print(f"Available tools: {[tool.name for tool in tools]}")
list_of_tools = ', '.join(tool_names)


# --- 1. Define the Prompt with Scratchpad ---
template = '''Answer the following questions as best you can. You have access to the following tools:

{tools}

Use the following format:
    
Information:  Do not use GROUP BY in the final cypher statment
Participant age is stored as age_at_enrollment
Cancer Type is stored in primary_disease_site

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Output:  Create a nice table displaying the results

Begin!

Question: {input}
Thought:{agent_scratchpad}'''
prompt = PromptTemplate.from_template(template)

agent = create_react_agent(model, tools, prompt) # Using ReAct pattern

agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, handle_parsing_errors=True,
                               return_intermediate_steps=True, tool_choice="auto")

# Invoke the agent
user_query = "participants with lung cancer, over the age of 50"
try:
    response = agent_executor.invoke({"input": user_query, "tools": tools, "agent_scratchpad": list_of_tools,
                                      "system": "Pull the schema first to ensure you know what the nodes are and where properties are stored"})
#    print(response)
except Exception as ex:
    print(ex)
    display_error_line(ex)


