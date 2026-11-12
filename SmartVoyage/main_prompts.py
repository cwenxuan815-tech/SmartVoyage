"""ChatService 全部提示词模板集中管理，便于调优与复用。"""
from langchain_core.prompts import ChatPromptTemplate


class SmartVoyagePrompts:
    """意图识别 / 规划 / ReAct 汇总 / 结果总结 / 景点推荐提示词。"""

    @staticmethod
    def intent_prompt() -> ChatPromptTemplate:
        return ChatPromptTemplate.from_template("""你是 SmartVoyage 旅行助手的意图识别器。结合历史对话、用户偏好和当前任务上下文，判断用户想做什么。

【当前日期】{current_date}
【短期对话】
{conversation_history}
【用户偏好】{user_profile}
【任务上下文】{task_context}
【用户本轮输入】{query}

【支持的意图】
weather(天气) / train(火车票) / flight(机票) / concert(演唱会票) / attraction(景点推荐) /
car_rental(租车) / tour_group(旅游团) / insurance(旅行保险) / order(票务预定) / trip_order(行程预定)
out_of_scope(与旅行完全无关)

【规则】
1. 一句话包含多个诉求时，输出多个意图；历史对话中的城市、日期、偏好可用于补全本轮省略的信息。
2. user_queries 的 key 必须与 intents 一一对应，value 是补全后的完整自然语言子查询。
3. 槽位（城市、日期等）缺失时不要在这里追问，交给对应的子代理追问，follow_up_message 保持空字符串。
4. 只有完全无法判断意图（闲聊、与旅行无关）时，intents 填 ["out_of_scope"] 并在 follow_up_message 写一句友好提示。
5. 只输出一个 JSON 对象，不要输出 Markdown 代码块或任何解释。

【输出格式】
{{"intents": ["weather"], "user_queries": {{"weather": "北京 2025-08-11 天气"}}, "follow_up_message": ""}}""")

    @staticmethod
    def planning_prompt() -> ChatPromptTemplate:
        return ChatPromptTemplate.from_template("""你是任务规划器。判断这些子任务之间是否存在依赖，需要按步骤串行执行。

【当前日期】{current_date}
【用户偏好】{user_profile}
【对话历史】{conversation_history}
【识别到的意图】{intents}
【各子查询】{user_queries}

【规则】
1. 若任务之间存在条件或数据依赖（例如"先查天气，天气好再订票"、"根据查到的车次下单"），need_plan 为 true，并给出有序 steps。
2. 完全独立的查询类任务，need_plan 为 false，steps 为空数组。
3. 每个 step 形如 {{"intent": "weather", "query": "子查询", "depends_on": []}}；depends_on 填所依赖的意图名。
4. 只输出 JSON。

【输出格式】
{{"need_plan": false, "reason": "各子查询相互独立，可并行执行", "steps": []}}""")

    @staticmethod
    def react_summary_prompt() -> ChatPromptTemplate:
        return ChatPromptTemplate.from_template("""你是 SmartVoyage 的结果整合助手。把各子代理的执行结果整合成一段连贯、友好的中文回复。

【用户问题】{query}
【用户偏好】{user_profile}
【各步骤执行结果】
{observations}

【要求】
1. 按用户提问的顺序组织内容，不要重复，不要编造结果里没有的数据。
2. 如果某一步是向用户追问，请保留该追问并放在最后，提示用户补充信息。
3. 适当给出简短出行建议，控制在 400 字以内。
4. 直接输出回复正文，不要输出 JSON 或标题。""")

    @staticmethod
    def attraction_prompt() -> ChatPromptTemplate:
        return ChatPromptTemplate.from_template("""你是一个资深旅行规划师。针对用户需求推荐 3~5 个景点或玩法。

【用户需求】{query}

请为每个推荐给出：名称、所在城市、亮点一句话、建议游玩时长。用中文分点输出，语气温和，不要编造门票价格等未经验证的数据。""")

    @staticmethod
    def summarize_weather_prompt() -> ChatPromptTemplate:
        return ChatPromptTemplate.from_template("""把天气查询结果整理成用户友好的中文回复，并给出出行建议。

【用户问题】{query}
【查询结果】{raw_response}

要求：按城市/日期列出天气现象、气温、湿度、风力、降水；最后给一句出行建议。不要输出原始 JSON，不要编造结果外的数据。""")

    @staticmethod
    def summarize_ticket_prompt() -> ChatPromptTemplate:
        return ChatPromptTemplate.from_template("""把票务/行程查询结果整理成用户友好的中文回复。

【用户问题】{query}
【查询结果】{raw_response}

要求：用分点列出车次/航班/艺人/产品名、时间、价格、余票或余量；若结果中包含向用户追问的话，请原样保留追问。不要输出原始 JSON，不要编造结果外的数据。""")
