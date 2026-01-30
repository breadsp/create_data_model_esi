# -*- coding: utf-8 -*-
"""
Created on Thu Jan 29 10:42:59 2026

@author: breadsp2
"""

import streamlit as st
import pandas as pd
import mgclient
from streamlit_agraph import agraph, Node, Edge, Config


pd.options.mode.chained_assignment = None

# Connection details (adjust as needed)
#memgraph = Memgraph(host='localhost', port=7687)
conn = mgclient.connect(host='127.0.0.1', port=7687)
mg = conn.cursor()

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
    mg.execute(query)
    result = mg.fetchall()
    
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

def check_for_nodes(node_names, final_df_edge):
    nodes_to_add = []
    for curr_node in node_names:
        match = final_df_edge.query(f"child == '{curr_node}' or parent == '{curr_node}'")
        found_list = list(match["child"]) + list(match["parent"])
        found_list = list(set(found_list))
        if len ([i for i in found_list if i in node_names]) > 1:  #link node found
            new_list = []
        else:
            new_list = [item for item in found_list if str(item) not in node_names]
        #print(new_list)
        
        if len(nodes_to_add) == 0:
            nodes_to_add = new_list
        elif len(new_list) > 0:
            nodes_to_add = list(set(nodes_to_add) & set(new_list))
    if len(nodes_to_add) > 0:
       # st.write("original nodes are not connected, adding linking nodes\n")
        node_names = node_names +  [i for i in nodes_to_add]
    
    return node_names

def make_schema(node_df, edge_df):
    nodes_agraph = [Node(id=node_df.loc[node, "index"], label=node_df.loc[node, "label"], 
                      size=25, shape="dot") for node in node_df.index]
    edges_agraph = [Edge(source=edge_df.loc[edge, 'index_x'], target=edge_df.loc[edge, 'index_y'], 
                     label="") for edge in edge_df.index]
                     #label=final_df_edge.loc[edge, 'label']) for edge in final_df_edge.index]

    config = Config(width=375, height=275, directed=True, fit=True,
                    nodeHighlightColor="#FFAE42", linkHighlightColor="#FFAE42",
                    displayNodeImage=True, enablePhysics=True , hierarchical=True,
                    nodeSpacing= 350, treeSpacing =  100, edgeMinimization = False,
                    direction = "UD", blockShifting = False
                    # Example of custom node/edge properties (adjust as needed)
                    # node_stable_colors=True, edge_stable_colors=True
                    )
#    with graph_window.container(border=True):
    agraph(nodes_agraph, edges_agraph, config)


    
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
            padding-top: 0rem; /* Adjust this value as needed */
            padding-left: 1rem;
            padding-right: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True)

st.markdown("<h1 style='text-align: center; color: black; font-size: 30px;'>Memgraph Graph Visualization</h1>", unsafe_allow_html=True)

graph_data = get_graph_data()

z = pd.DataFrame(graph_data["nodes"])

temp = {i: j for j, i in enumerate(set(z["label"]))}
res = [temp[i] for i in z["label"]]
for idx in range(0,len(res)):
    graph_data["nodes"][idx]["index"] = res[idx]
  

edge_df = pd.DataFrame(graph_data["edges"])
node_df = pd.DataFrame(graph_data["nodes"])
new_edges = edge_df.merge(node_df[["id","index"]], left_on="source", right_on="id")
new_edges = new_edges.merge(node_df[["id","index"]], left_on="target", right_on="id")

node_df.drop_duplicates("index", inplace=True)
final_df_edge = new_edges.drop_duplicates(["index_x", "index_y"])

node_df.drop("id", axis=1, inplace=True)
final_df_edge.drop(["source", "target"], axis=1, inplace=True)

final_df_edge["index_x"] = final_df_edge["index_x"].astype(str)
final_df_edge["index_y"] = final_df_edge["index_y"].astype(str)
node_df["index"] = node_df["index"].astype(str)
node_df.reset_index(inplace=True)

if "selected_properties" not in st.session_state:
    st.session_state.selected_properties = ['']*len(node_df)
    
if "dict_keys" not in st.session_state:
    st.session_state.dict_keys = list(node_df["label"])
    
if "query" not in st.session_state:
    st.session_state.query = ""
    
    
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



# Set page configuration to make sure sidebar is visible by default (optional)
#st.set_page_config(initial_sidebar_state="expanded")

with st.sidebar.form(key='my_nodes'):        
    for curr_idx in node_df.index:
        st.session_state.selected_properties[curr_idx] = st.sidebar.multiselect(
        label=node_df.loc[curr_idx]["label"],
        options=list(node_df.loc[curr_idx]["properties"].keys())
    )
    submit_button = st.form_submit_button(label='Apply Selections')

user_window = st.empty()
output_window = st.empty()



with user_window.container(border=True):
    col_1, col_2 = st.columns([1,2])
    if submit_button:  
        st.session_state.query = ""
  #      st.write("User Selected: ")
        result_dict =  dict(zip(st.session_state.dict_keys, st.session_state.selected_properties))
        node_names = [i for i in result_dict if len(result_dict[i]) > 0]
        #node_index = list(node_df.query(f"label in {node_names}")["index"])
        #st.write(f"{node_names} : {node_index}")
   #     st.write(f"Original: {node_names}")
        
        node_names = check_for_nodes(node_names, final_df_edge)
    #    st.write(f"Updated: {node_names}")
     
        output_list = []
        query = ""         
        for child_node in node_names:
            for parent_node in node_names:
                print(f"child: {child_node} is looking for parent: {parent_node}")
                match = final_df_edge.query(f"child == '{child_node}' and parent == '{parent_node}'")
                if len(match) > 0:
                    parent_name = match.iloc[0]["parent"]
                    parent_node = match.iloc[0]["index_y"]
                    child_name = match.iloc[0]["child"]
                    child_node = match.iloc[0]["index_x"]
                    relationship = match.iloc[0]["label"]
                    
                    output_list = output_list + [f"node_{child_node}.{i}" for i in result_dict[child_name]]
                    output_list = output_list + [f"node_{parent_node}.{i}" for i in result_dict[parent_name]]
                    
                    st.session_state.query += f"match(node_{child_node}: {child_name}) -[:{relationship}]- (node_{parent_node}: {parent_name})\n"
        
        graph_node_df = node_df.query(f"label in {node_names}")
        matching_list = graph_node_df['index'].tolist()
        edge_df = final_df_edge.query(f"index_x in {matching_list} or index_y in {matching_list}")
        with col_1:
            make_schema(graph_node_df, edge_df)
        with col_2:
             st.write("=" * 50)
             output_list = list(set(output_list))
             output_list = [test + " as " + test[test.find('.')+1:] for test in output_list]
             
             output_str = ", ".join(output_list)
             st.session_state.query += f"\n Return {output_str}"
             st.write(st.session_state.query)
             st.write("=" * 50)
                     
            
with output_window.container(border=True):
    st.write("here is the output")
    if len(st.session_state.query) > 0:
        mg.execute(st.session_state.query)
        result = mg.fetchall()
        for record in result:
            st.write(record)
    