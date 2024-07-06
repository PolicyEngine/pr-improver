import streamlit as st
import uuid
import json


def copy_button(text_to_copy, button_text):
    button_id = str(uuid.uuid4())
    st.markdown(
        f"""
    <style>
    #{button_id} {{
        background-color: rgb(255, 255, 255);
        color: rgb(38, 39, 48);
        padding: 0.25em 0.38em;
        position: relative;
        text-decoration: none;
        border-radius: 4px;
        border-width: 1px;
        border-style: solid;
        border-color: rgb(230, 234, 241);
        border-image: initial;
    }}
    #{button_id}:hover {{
        border-color: rgb(246, 51, 102);
        color: rgb(246, 51, 102);
    }}
    #{button_id}:active {{
        box-shadow: none;
        background-color: rgb(246, 51, 102);
        color: white;
    }}
    </style>""",
        unsafe_allow_html=True,
    )

    escaped_text = json.dumps(text_to_copy)

    st.markdown(
        f"""
    <button id="{button_id}" onclick="
    navigator.clipboard.writeText({escaped_text});
    this.innerHTML='Copied!';
    setTimeout(() => this.innerHTML='{button_text}', 1000)
    ">{button_text}</button>
    """,
        unsafe_allow_html=True,
    )
