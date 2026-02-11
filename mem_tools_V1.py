## 1)  load all necessary librarys to run this agent 
from langchain.tools import tool
import mgclient
import pandas as pd
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_ollama import ChatOllama
from langchain_classic.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

## 2) create a class that has the memgraph connection 
class Memgraph_DB():
    def __init__(self):
        self.host = "127.0.0.1"
        self.port =  7687
        self.username = ""
        self.password = ""
        
        self.conn = mgclient.connect(host=self.host, port=self.port) #, username=self.username, password=self.password)
        self.cursor = self.conn.cursor()

MEM_DB = Memgraph_DB()

## 3) create a list of tools and subfunctions necessary to run
@tool
def query_memgraph(user_question: str):
    """Use this tool to ask questions about the graph database. 
    It automatically looks up schema and generates the query."""
    
    # Step 1: Internal call to get schema
    schema = get_memgraph_schema()
    print("\nschema has been generated and passing to parser")
    
    # Step 2: Internal call to extract metadata
    metadata = extract_relevant_metadata(user_question, schema)
#    print(f"\n {metadata}")
    print("\n parser has been completed and moving to cypher creation")
    
    # Step 3: Generate and execute
    #query = generate_and_execute_cypher(user_question, metadata)
    #return memgraph.execute_and_fetch(query)
    MEM_DB.conn.close()
    return metadata

def get_memgraph_schema(): #, username="mem_user", password="mempass26!") -> str:
    """
    Retrieves the graph database schema from Memgraph. 
    Use this tool when you need to know the available Node labels, 
    Relationship types, and their associated properties to construct a Cypher query.
    Returns a JSON structure of nodes and relationships
    """
    try:        
        query = "CALL llm_util.schema('raw') YIELD schema RETURN schema;"
        MEM_DB.cursor.execute(query)
        full_graph = MEM_DB.cursor.fetchall()
        full_graph = full_graph[0][0]
        node_dict = []
        for curr_node in full_graph["node_props"]:
            node_dict.append(
            {
                "label": curr_node,
                "properties": [i["property"] for i in full_graph["node_props"][curr_node]
                               if ("original" not in i or "_unit" not in i)],
                "description": curr_node
            })
        
        MEM_DB.cursor.execute("""
            MATCH (n)-[r]->(m)
            WITH DISTINCT labels(n)[0] AS start_node, type(r) AS rel_type, labels(m)[0] AS end_node
            RETURN start_node, rel_type, end_node; """)

        rel_paths = [
            f"(:{r[0]})-[:{r[1]}]->(:{r[2]})" 
            for r in MEM_DB.cursor.fetchall()
        ]
        return {
            "node_definitions": node_dict,
            "relationship_paths": rel_paths
        }
                
    except Exception as e:
        return f"Error connecting to Memgraph or fetching schema: {str(e)}"


#    Identify the Node Labels, Relationships, Properties, Filter_Criteria, and Grouping_Criteria needed for this request:

def extract_relevant_metadata(user_question: str, schema: str):
    """
    Input: users query and output schema from tool call get_memgraph_schema
    Output: a list of nodes, properties and relationships related to the user query
    """
    
    llm = ChatOllama(temperature=0, model="llama3.2:3b")
    extract_prompt = ChatPromptTemplate.from_template("""
    You are a graph database expert. Based on the following Memgraph schema:
    {schema}
    
    Cancer information is located in the node: Diagnosis with property: primary_disease_site
    
    The user is requesting the following question: 
    {user_input}
    
    Grouping_Criteria will overlap with Properties if applicable
    
    Return results as a dictionary with keys being 
        - Node_Labels (all necessary nodes),
        - Relationships (all relationships between nodes),
        - Properties (all properties user asked for)
        - Filter_Criteria (any filtering user asked for)
        - Grouping Criteria (any grouping of data the user wants)
    Do Not return anything else
    Do Not attempt to make a cypher using this data
    
    Output only the relevant components in a python dictionary
    """)
#   Output only the relevant components in a concise list.
  
    print("\nanalyizing the provided schema and extracting the key elements")
    chain = extract_prompt | llm | StrOutputParser()
    return chain.invoke({"schema": schema, "user_input": user_question})


def generate_and_execute_cypher(user_prompt, extraction_results, 
                                host="127.0.0.1", port=7687): #, username="mem_user", password="mempass26!"):
    """
    Translates the extracted metadata into a Cypher query and executes it.
    """
    extraction_results.find("Node Labels:")
    extraction_results.find("Relationships:")
    extraction_results.find("Properties:")
    
    #print(extraction_results)
    
    # 1. Generate the Query using Llama/LLM
    # We pass ONLY the relevant subset of the schema to keep the prompt clean
 
#       RELEVANT SCHEMA SUBSET:
#    Nodes: {extraction_results.get('nodes')}
#    Relationships: {extraction_results.get('relationships')}
#    Properties: {extraction_results.get('properties')}

    
    system_prompt = f"""
    You are a Memgraph Cypher expert.
    {extraction_results}
    
    TASK:
    Write a Cypher query to answer: "{user_prompt}"
    
    RULES:
    - Use ONLY the labels and properties provided above.
    - Return ONLY the raw Cypher string.
    - No markdown formatting, no backticks, no explanations.
    """

    # (Assuming 'llm' is your Llama/LangChain instance from previous steps)
    cypher_query = llm.invoke(system_prompt).content.strip()

    # 2. Execute via mgclient
    conn = mgclient.connect(host=host, port=port) #, username=username, password=password)
#    conn.autocommit = True
    cursor = conn.cursor()

    try:
        print(f"--- Executing Cypher ---\n{cypher_query}\n-----------------------")
        cursor.execute(cypher_query)
        
        # Fetch results and column names for a readable output
        print(cursor.description)
        columns = [desc[0] for desc in cursor.description]
        results = cursor.fetchall()
        df = pd.DataFrame(results, columns=columns)
   #     results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return df

    except mgclient.DatabaseError as e:
        return f"Database Error: {str(e)}"
    finally:
        cursor.close()
        conn.close()    
    

## 4) set up the main function
def main():

    # Initialize the LLM
    llm = ChatOllama(temperature=0, model="llama3.2:3b")
    
    # Define the set of tools available to the agent
    tools = [query_memgraph]
        
    template = '''Answer the following questions as best you can. You have access to the following tools:  
    
    {tools}
        
    Use the following format:
    
    Question: the input question you must answer
    Thought: you should always think about what to do
    Action: the action to take, should be one of [{tool_names}]
    Action Input: this shoudl be the users Question
    Observation: the result of the action
    Thought: I now know the final answer
    Final Answer: the final answer to the original input question
    
    Begin!
    
    Question: {input}
    Thought:{agent_scratchpad}'''
    prompt = PromptTemplate.from_template(template)
    
    
    agent = create_react_agent(llm, tools, prompt) # Using ReAct pattern
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, 
                                   return_intermediate_steps=True, max_iterations=1)
    
    # 3. Invoke the agent
    user_query = "Top 5 cancer types for people between 55 and 75 years old?"
    
    try:
        response = agent_executor.invoke({"input": user_query, "tools": tools, "agent_scratchpad": "", 
                                          "tool_names": 'query_memgraph', 
                                          "system": "Look at the database and extract relevant information related to the users question"})
    #    print(response)
    except Exception as ex:
        print(ex)
    
if __name__ == '__main__':
    main()