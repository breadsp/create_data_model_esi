# -*- coding: utf-8 -*-
"""
Created on Thu Jan 29 10:42:59 2026

@author: breadsp2
"""

import streamlit as st
import pandas as pd
import mgclient
import re

from streamlit_agraph import agraph, Node, Edge, Config
from langchain_anthropic import ChatAnthropic

from langchain_memgraph.graphs.memgraph import MemgraphLangChain
from langchain_memgraph.toolkits import MemgraphToolkit
from langchain_classic.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

pd.options.mode.chained_assignment = None

# Streamlit Page Configuration
# --- Streamlit UI ---

st.set_page_config(layout="wide")
st.set_page_config(page_title="Memgraph AI Query Interface", page_icon="🧠", layout="wide")

title_alignment = """
    <style>
    .centered-title {
        text-align: center;
    }
    </style>
"""

st.markdown(title_alignment, unsafe_allow_html=True)
st.markdown(
        """
        <style>
        .block-container {
            padding-top: 0px; /* Adjust this value as needed */
            padding-left: 1rem;
            padding-right: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True)

st.markdown("""
<style>
.no-space {
    margin: 0;
    padding: 0;
    line-height: 0; /* Adjust as needed for minimal spacing */
}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='no-space' style='text-align: center; color: black; font-size: 30px; font-weight: bold;'>AI Data Assistant Chatbot</h1> " +
            "<p class='no-space' style='text-align: center; color: black; font-size: 15px;'>Ask questions about your graph database using natural language</p>",
             unsafe_allow_html=True)

# get API KEY
ANTHROPIC_API_KEY = "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"
model = ChatAnthropic(model="claude-sonnet-4-5-20250929", api_key=ANTHROPIC_API_KEY )

class Memgraph_DB():
    def __init__(self):
        self.host = "127.0.0.1"
        self.port =  7687
        self.username = "memuser"
        self.password = "mempass26!"
    def connect_to_db(self): 
        self.conn = mgclient.connect(host=self.host, port=self.port, username=self.username, password=self.password)
        self.cursor = self.conn.cursor()

def get_memgraph_client():
    """Establishes and caches a connection to Memgraph."""
    mem_db = Memgraph_DB()
    try:
        mem_db.connect_to_db()
    except Exception as e:
        print(e)
        st.error(f"Error connecting to Memgraph: {e}")
        return None
    return mem_db

if "mem_db" not in st.session_state:
     st.session_state.mem_db =  get_memgraph_client()
     memgraph_url = f"bolt://localhost:{st.session_state.mem_db.port}"
     db = MemgraphLangChain(url=memgraph_url, username=st.session_state.mem_db.username, password=st.session_state.mem_db.password)

def get_mem_tools(db):
    toolkit = MemgraphToolkit(db=db, llm=model)
    tools = toolkit.get_tools()
    #tools = [tool for tool in tools if tool.name not in ["run_cypher"]]
    
    return tools

if "tools" not in st.session_state:
    st.session_state.tools =  get_mem_tools(db)
    
if "list_of_tools" not in st.session_state:
    tool_names = [tool.name for tool in st.session_state.tools]
    st.session_state.list_of_tools = ', '.join(tool_names)

if "response" not in st.session_state:
    st.session_state.response = ""
    
def create_agent(tools, model):
    template = '''Answer the following questions as best you can. You have access to the following tools:
    
    {tools}
    
    Use the following format:
        
    Information:  Do not use GROUP BY in the final cypher statment
    Participant age is stored as age_at_enrollment
    Cancer Type is stored in primary_disease_site
    
    Cypher Rules:
        when the variable is not a number then use the following filtering format WHERE ANY(term IN [term] WHERE tolower(variable) CONTAINS term) 
        lowercase all values expcet for the Cypher Key Words
        Only use enough tools to generate the Cypher
        Do no use " in the return statement, use ` instead

    
    Question: the input question you must answer
    Thought: you should always think about what to do
    Action: the action to take, should be one of [{tool_names}]
    Action Input: the input to the action
    Observation: the result of the action
    ... (this Thought/Action/Action Input/Observation can repeat N times)
    Thought: I now know the final answer and have the final cypher I need
    Final Answer: the final answer to the original input question
    
    Begin!
    
    Question: {input}
    Thought:{agent_scratchpad}'''
    prompt = PromptTemplate.from_template(template)
    
    agent = create_react_agent(model, tools, prompt) # Using ReAct pattern
    
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=False, handle_parsing_errors=True,
                                   return_intermediate_steps=False, tool_choice="auto")
    return agent_executor
    
if "agent_executor" not in st.session_state:
    st.session_state.agent_executor = create_agent(st.session_state.tools, model)
    

def drop_date(node,date_str):
    if date_str in node.properties:
        node.properties.pop(date_str)
    return node

def get_graph_data():
    # Example Cypher query: adjust to your specific data model
    query = """
    MATCH (n)-[r]->(m)
    RETURN n, r, m
    """
    nodes = {}
    edges = []
    st.session_state.mem_db.cursor.execute(query)
    result = st.session_state.mem_db.cursor.fetchall()
#    columns = [desc.name for desc in mg.description]
#    df = pd.DataFrame(result, columns=columns)
    
    for record in result:
        n = record[0]  #['n']  
        m = record[2]  #['m']  
        r = record[1]  #['r']
        # Add nodes to a dictionary to avoid duplicates
        if n.id not in nodes:
            nodes[n.id] = {"id": n.id, "label": list(n.labels)[0], "properties": n.properties}
        if m.id not in nodes:
            nodes[m.id] = {"id": m.id, "label": list(m.labels)[0], "properties": m.properties}
   
        n = drop_date(n, "created")
        r = drop_date(r, "created")
        m = drop_date(m, "created")

        n = drop_date(n, "modified")
        r = drop_date(r, "modified")
        m = drop_date(m, "modified")

        
        # Add edges
        edges.append({"child": list(n.labels)[0], "source": n.id, "parent": list(m.labels)[0], "target": m.id, "label": r.type, "properties": r.properties})
        
    # Format data for the visualization component (usually list of nodes and edges)
    graph_data = {
        "nodes": list(nodes.values()),
        "edges": edges
    }
    return graph_data

def make_schema(node_df, edge_df):
    nodes_agraph = [Node(id=node_df.loc[node, "index"], label=node_df.loc[node, "label"], 
                      size=25, shape="dot", color = node_df.loc[node, "color"]) for node in node_df.index]
# color="#FF0000")) # Red
# color="#00FF00")) # Green
    
    edges_agraph = [Edge(source=edge_df.loc[edge, 'index_x'], target=edge_df.loc[edge, 'index_y'], 
                     label="") for edge in edge_df.index]
                     #label=final_df_edge.loc[edge, 'label']) for edge in final_df_edge.index]

    config = Config(height=300,  width=600, directed=True, fit=True,
                    nodeHighlightColor="#FFAE42", linkHighlightColor="#FFAE42",
                    displayNodeImage=True, enablePhysics=True , hierarchical=True,
                    nodeSpacing= 350, treeSpacing =  200, edgeMinimization = False,
                    direction = "LR", blockShifting = False
                    # Example of custom node/edge properties (adjust as needed)
                    # node_stable_colors=True, edge_stable_colors=True
                    )
#    with graph_window.container(border=True):
    return nodes_agraph, edges_agraph, config

if "cypher_str" not in st.session_state:
    st.session_state.cypher_str = ""

if "graph_data" not in st.session_state:
    st.session_state.graph_data = get_graph_data()
    z = pd.DataFrame(st.session_state.graph_data["nodes"])
    
    temp = {i: j for j, i in enumerate(set(z["label"]))}
    res = [temp[i] for i in z["label"]]
    for idx in range(0,len(res)):
        st.session_state.graph_data["nodes"][idx]["index"] = res[idx]
  
if "node_df" not in st.session_state and "final_df_edge" not in st.session_state:
    st.session_state.node_df = pd.DataFrame(st.session_state.graph_data["nodes"])
    edge_df = pd.DataFrame(st.session_state.graph_data["edges"])

    new_edges = edge_df.merge(st.session_state.node_df[["id","index"]], left_on="source", right_on="id")
    new_edges = new_edges.merge(st.session_state.node_df[["id","index"]], left_on="target", right_on="id")
    
    st.session_state.node_df.drop_duplicates("index", inplace=True)
    st.session_state.final_df_edge = new_edges.drop_duplicates(["index_x", "index_y"])
    
    st.session_state.node_df.drop("id", axis=1, inplace=True)
    st.session_state.final_df_edge.drop(["source", "target"], axis=1, inplace=True)
    
    st.session_state.final_df_edge["index_x"] = st.session_state.final_df_edge["index_x"].astype(str)
    st.session_state.final_df_edge["index_y"] = st.session_state.final_df_edge["index_y"].astype(str)
    st.session_state.node_df["index"] = st.session_state.node_df["index"].astype(str)
    st.session_state.node_df["color"] = "#87CEFA"   #blue nodes
    st.session_state.node_df.reset_index(inplace=True)

    
st.markdown("""
<style>
    /* Targets the label of the multiselect widget */
    .stMultiSelect > label {
        font-size: 12px; /* Adjust the size as needed */
        color: gray; /* Optional: change color */
    }

    /* Targets the text of the selected options inside the multiselect box */
    .stMultiSelect [data-baseweb="select"] span {
        font-size: 8px; /* Adjust the size as needed */
    }
</style>
""", unsafe_allow_html=True)



user_window = st.empty()
schema_col, user_col = st.columns([3, 2])

with schema_col:
    show_schema, schema_table = st.tabs(["Visualize Schema", "Schema as Table"])
            
    with show_schema:
        nodes_agraph, edges_agraph, config = make_schema(st.session_state.node_df, st.session_state.final_df_edge)
        agraph(nodes_agraph, edges_agraph, config)

    with schema_table:
        st.dataframe(st.session_state.final_df_edge[["child", "label", "parent"]])

with user_col:
    user_input, cypher_output, result_table, user_output = st.tabs(["User Query", "Cypher Code", "Result Table", "Summary"])
    
    with user_input:
        user_query = st.text_area(
            "🔍 Enter your query:",
            placeholder="e.g., count of all participants",
            height=80,
            key="user_query_input"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            submit_button = st.button("🚀 Run Query", type="primary", use_container_width=True)
        with col2:
            clear_button = st.button("🗑️ Clear", use_container_width=True)
        
        if clear_button:
            st.rerun()
            
    if submit_button and user_query:
        st.divider()
        error_count = 0
        try:
            st.session_state.response = st.session_state.agent_executor.invoke({
                "input": user_query,
                "tools": st.session_state.tools, 
                "agent_scratchpad": st.session_state.list_of_tools,
                "system": "Pull the schema first to ensure you know what the nodes are and where properties are stored"
            })
            st.success("✅ Query completed!")
            #st.write(st.session_state.response["output"])
            
            if "output" in st.session_state.response:
                output_str = st.session_state.response["output"]
                st.session_state.cypher_str = output_str[output_str.find("```"):output_str.find("```\n")]

        except Exception:
            st.error("❌ Query failed!")
        finally:
            st.rerun()
            
    
    with cypher_output:

        if st.session_state.cypher_str != "":
            print(st.session_state.response["output"]) 
            st.write(st.session_state.cypher_str)
         #   print(st.session_state.response[curr_key])
                
            pattern = r"([a-z]{1}:[a-z]+)"
            matches = re.findall(pattern, st.session_state.cypher_str)
            node_names = [i[2:] for i in matches]
            
            x = st.session_state.node_df.query(f"label in {node_names}")
            st.session_state.node_df.loc[x.index, "color"] = "#00FF00"
        else:
            st.write("no cypher statement was created")
                
    with result_table:
        if st.session_state.cypher_str != "":
        #    print("here is the cypher\n")
            query = st.session_state.cypher_str.replace("```cypher","")
            query = query.replace("```","")
            query = query.replace("``","")
         #   print(query)
            
            st.session_state.mem_db.cursor.execute(query)
            result = st.session_state.mem_db.cursor.fetchall()
            columns = [desc.name for desc in st.session_state.mem_db.cursor.description]
            df = pd.DataFrame(result, columns=columns)
            st.dataframe(df)
        else:
            st.write("no data to display")    
        
            
    with user_output:
        st.write("here is the output")
       # st.write(f"the response file is : {st.session_state.response}")
        for curr_key in st.session_state.response:
            if curr_key == "output":
                output_str = st.session_state.response[curr_key]
                display_str = output_str[(output_str.find("```\n\n")+5):]
                st.write(display_str)
              #  print(st.session_state.response[curr_key])
                
            
                      
