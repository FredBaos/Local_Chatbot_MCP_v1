from flask import Flask, render_template, request, jsonify
from mlx_lm import load, generate
import mlx.core as mx
import sys, os, csv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from rag_engine.storage.database import (
    init_db,
    save_message,
    get_session_history,
    get_all_sessions,
    delete_session_history,
)
from rag_engine.storage.chroma_memory import (
    add_memory,
    delete_session_memory,
    retrieve_memory,
)
# Import the new external reference knowledge layer
from rag_engine.storage.chroma_knowledge import query_knowledge
from rag_engine.utils.rag_support import get_rag_setup_context

app = Flask(__name__)
init_db()

mx.set_default_device(mx.Device(mx.gpu))
MODEL_NAME = "mlx-community/Llama-3.2-3B-Instruct-4bit"
model, tokenizer = load(MODEL_NAME)

MODEL_DISPLAY_NAME = MODEL_NAME.split("/")[-1]
MODEL_PARAMETER_LABEL = "≈3B params (4-bit quantized)"
RECENT_MESSAGE_WINDOW = 10
LONG_TERM_MEMORY_LIMIT = 5
EXTERNAL_KNOWLEDGE_LIMIT = 2

@app.route('/')
def home():
    return render_template(
        'index.html',
        model_name=MODEL_DISPLAY_NAME,
        model_parameters=MODEL_PARAMETER_LABEL,
    )


@app.route('/sessions')
def sessions():
    return jsonify(get_all_sessions())


@app.route('/history/<session_id>')
def history(session_id):
    return jsonify(
        {
            "session_id": session_id,
            "messages": get_session_history(session_id, limit=1000),
        }
    )


@app.route('/delete-session/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    delete_session_history(session_id)
    deleted_memory_count = delete_session_memory(session_id)
    return jsonify({
        "success": True,
        "session_id": session_id,
        "deleted_memory_count": deleted_memory_count,
    })


@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json() or {}
    user_text = (data.get("text") or "").strip()
    session_id = data.get("session_id") or "default_user_session"

    if not user_text:
        return jsonify({"error": "No text provided"}), 400

    try:
        # 1. SQLite short-term conversational context flow
        recent_history = get_session_history(
            session_id,
            limit=RECENT_MESSAGE_WINDOW,
        )

        # 2. Chroma long-term chat cross-talk retrieval
        retrieved_facts = retrieve_memory(
            user_text,
            limit=LONG_TERM_MEMORY_LIMIT,
            exclude_session_id=session_id,
        )
        
        # 3. New external knowledge document stores retrieval
        news_context = query_knowledge(collection_name="tech_news", query_text=user_text, limit=EXTERNAL_KNOWLEDGE_LIMIT)
        specs_context = query_knowledge(collection_name="car_specs", query_text=user_text, limit=EXTERNAL_KNOWLEDGE_LIMIT)

        # Build prompt structural segments cleanly
        context_parts = []

        rag_setup_context = get_rag_setup_context(user_text)
        if rag_setup_context:
            context_parts.append(
                "RAG setup guidance:\n"
                + rag_setup_context
            )
        
        if news_context:
            context_parts.append(
                "External Tech News Articles:\n"
                + "\n".join(f"- {item['text']} (Source: {item['metadata'].get('title', 'Web Document')})" for item in news_context)
            )
            
        if specs_context:
            context_parts.append(
                "External Tabular Specifications:\n"
                + "\n".join(f"- {item['text']}" for item in specs_context)
            )

        if retrieved_facts:
            context_parts.append(
                "Long-term memory from other chats:\n"
                + "\n".join(f"- {item['text']}" for item in retrieved_facts)
            )
            
        if recent_history:
            context_parts.append(
                "Recent chat flow:\n"
                + "\n".join(
                    f"- {message['role']}: {message['content']}"
                    for message in recent_history
                )
            )

        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. Use the context provided below "
                    "when it is relevant and do not claim memory unless the context supports it."
                ),
            },
            {
                "role": "user",
                "content": (
                    ("\n\n".join(context_parts) if context_parts else "")
                    + ("\n\n" if context_parts else "")
                    + f"Question: {user_text}"
                ),
            },
        ]

        prompt = tokenizer.apply_chat_template(
            prompt_messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        ai_response = generate(
            model,
            tokenizer,
            prompt=prompt,
            max_tokens=512,
            verbose=False,
        )

        # Save context references and outputs after model verification loop
        save_message(session_id, "user", user_text)
        save_message(session_id, "assistant", ai_response)
        add_memory(session_id, "user", user_text)
        add_memory(session_id, "assistant", ai_response)
        
        return ai_response.strip()

    except Exception as e:
        return jsonify({"error": f"MLX Inference Error: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(threaded=False)