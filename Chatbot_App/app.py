from flask import Flask, render_template, request, jsonify, Response, stream_with_context
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
    add_paired_memory,
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
EXTERNAL_KNOWLEDGE_LIMIT = 5

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

        # Build prompt messages using real chat turns for better behavior
        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. Use the context provided below when it is relevant "
                    "and do not claim memory unless the context supports it. When a question is about "
                    "news, car listings, or other facts covered by an 'External' context block, you "
                    "must answer using ONLY the numbered items in that block — do not mention a "
                    "knowledge cutoff, and do not add any company, product, car, price, or event that "
                    "is not explicitly listed there. List every item provided, each as its own bullet, "
                    "even if a fragment reads awkwardly out of context — summarize it as best you can "
                    "rather than skipping it. If the block is missing or doesn't cover the question, "
                    "say so explicitly instead of filling the gap with unverified information."
                ),
            },
        ]

        # Add RAG setup and external knowledge as system-level context blocks
        rag_setup_context = get_rag_setup_context(user_text)
        if rag_setup_context:
            prompt_messages.append({"role": "system", "content": "RAG setup guidance:\n" + rag_setup_context})

        if news_context:
            numbered_news = "\n".join(
                f"{i}. {item['text'].replace(chr(10), ' ')} (Source: {item['metadata'].get('title', 'Web Document')})"
                for i, item in enumerate(news_context, start=1)
            )
            prompt_messages.append({
                "role": "system",
                "content": f"External Tech News Articles:\n{numbered_news}",
            })

        if specs_context:
            numbered_specs = "\n".join(
                f"{i}. {item['text']}" for i, item in enumerate(specs_context, start=1)
            )
            prompt_messages.append({
                "role": "system",
                "content": (
                    f"External Tabular Specifications (these are the only {len(specs_context)} "
                    "real listings available — do not describe any other car, generation, "
                    "variant, or award from your own training data, even if asked to "
                    "'tell me about' a car in general):\n"
                    f"{numbered_specs}"
                ),
            })

        # Append recent chat history as real turn messages
        if recent_history:
            for message in recent_history:
                # Ensure roles are familiar to the tokenizer (user/assistant/system)
                role = message.get("role", "user")
                prompt_messages.append({"role": role, "content": message.get("content", "")})

        # Add long-term retrieved facts as system hints (already filtered by threshold)
        if retrieved_facts:
            prompt_messages.append({"role": "system", "content": "Long-term memory from other chats:\n" + "\n".join(f"- {item['text']}" for item in retrieved_facts)})

        # Finally, append the current user question as the active user turn. When
        # external context is present, restate the "don't invent items" constraint
        # here too — models weight instructions closer to generation much more
        # heavily than ones earlier in the system messages.
        question_content = f"Question: {user_text}"
        if news_context or specs_context:
            question_content += (
                "\n\nReminder: answer only using the numbered items in the External "
                "context block(s) above. Do not suggest or mention any company, product, "
                "car, or event that is not explicitly present there."
            )
        prompt_messages.append({"role": "user", "content": question_content})

        prompt = tokenizer.apply_chat_template(prompt_messages, tokenize=False, add_generation_prompt=True)

        ai_response = generate(model, tokenizer, prompt=prompt, max_tokens=512, verbose=False)

        # Save context references and outputs after model verification loop
        save_message(session_id, "user", user_text)
        save_message(session_id, "assistant", ai_response)

        # Persist paired memory (single document) for better association
        add_paired_memory(session_id, user_text, ai_response)

        # Streaming support: if client requests streaming, return a generator response
        if data.get("stream"):
            def generate_stream(text: str, chunk_size: int = 256):
                for i in range(0, len(text), chunk_size):
                    yield text[i : i + chunk_size]

            return Response(stream_with_context(generate_stream(ai_response)), mimetype="text/plain")

        return ai_response.strip()

    except Exception as e:
        return jsonify({"error": f"MLX Inference Error: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(threaded=False)