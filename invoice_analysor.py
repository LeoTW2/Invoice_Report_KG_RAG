from datetime import datetime
from openai import OpenAI
import pandas as pd
import anthropic
import re
from py2neo import Graph, Node, Relationship


class Financial_report:
  def __init__(self):
    #claude3
    self.claude_api_key = ''
    self.claude_client = anthropic.Anthropic(api_key = self.claude_api_key)
    self.claude_prompt = ''
    self.claude_system_prompt = ''
    self.purchase_table = ''
    self.cost_change_table = None
    #gpt
    self.gpt_api_key = ''
    self.gpt_client = OpenAI(api_key = self.gpt_api_key)
    self.gpt_system_prompt = ''
    self.gpt_prompt = ''
    #neo4j
    self.graph = Graph("", auth=("neo4j", ""))
    self.query = ''
    #other
    self.gen_image = None
    self.alert_category = None
    self.nfa = None
    self.today = '2024/04/01'.split('/')#datetime.now().strftime("%Y/%m/%d").split('/')

  def generate_query(self, member_uid, ac=None):
    if self.task == 'month_alert':
      self.query = f'''
                    MATCH (member:Member {{m_uid: '{member_uid}'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                    MATCH (invoice)-[p:PURCHASE]->(item:Item)
                    WHERE (date.month IN {[i for i in range((int(self.today[1])-(self.nfa+1)), int(self.today[1])-1)]}) AND date.year = {self.today[0]}
                    WITH date.month AS month, item.item_category AS category, item.item_price AS price, p.item_quantity AS quantity
                    WITH category, SUM(price * quantity)/COUNT(DISTINCT month) AS avg_spending

                    MATCH (member:Member {{m_uid: '{member_uid}'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                    MATCH (invoice)-[p:PURCHASE]->(item:Item)
                    WHERE date.month = {int(self.today[1])-1} AND date.year = {self.today[0]}
                    WITH category, avg_spending, item.item_category AS march_category, SUM(item.item_price * p.item_quantity) AS march_spending
                    WHERE category = march_category

                    RETURN category, avg_spending, march_spending, ((march_spending - avg_spending)/avg_spending) AS spending_difference
                    ORDER BY category
                    '''
    elif self.task == 'analysis_alert':
      self.query = f'''
                      MATCH (member:Member {{m_uid: '{member_uid}'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      MATCH (invoice)-[:RECEIVE_FROM]->(store:Store)
                      WHERE item.item_category = '{ac}' AND date.month IN {[i for i in range((int(self.today[1])-(self.nfa+1)), int(self.today[1]))]}
                      RETURN date.month AS month, store.store_name AS store_name, item.item_name AS item_name, item.item_price AS item_price, p.item_quantity AS item_quantity,
                      (item.item_price * p.item_quantity) AS total_spending, date.year AS purchase_year, date.month AS purchase_month, date.day AS purchase_day
                      ORDER BY purchase_year, purchase_month, purchase_day
                    '''
    elif self.task == 'generate_dataframe':
      self.query = f'''
                    MATCH (member:Member {{m_uid: '{member_uid}'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                    MATCH (invoice)-[p:PURCHASE]->(item:Item)
                    MATCH (invoice)-[:RECEIVE_FROM]->(store:Store)
                    WHERE (date.month IN {[i for i in range((int(self.today[1])-(self.nfa+1)), int(self.today[1]))]}) AND date.year = {self.today[0]}
                    RETURN date.month AS month, store.store_name AS store_name, item.item_name AS item_name, item.item_price AS item_price, p.item_quantity AS item_quantity,
                    (item.item_price * p.item_quantity) AS total_spending, date.year AS purchase_year, date.month AS purchase_month, date.day AS purchase_day,
                    item.item_category AS category
                    ORDER BY purchase_year, purchase_month, purchase_day
                    '''

  def claude(self, system_prompt, prompt):
    message = self.claude_client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1000, 
        temperature=0,
        system=system_prompt,
        messages=[
             {"role": "user", "content": prompt}
        ]
    )

    return message.content[0].text.replace('根據列表內容分析,','').replace('根據列表內容,','').replace('根據列表資料顯示,','').replace('根據列表資訊,','')#replace with re lib

  def gpt(self, system_prompt, prompt, model_name):
    completion = self.gpt_client.chat.completions.create(
    temperature = 0,
    model = model_name,
    messages=[
      {"role": "system", "content": system_prompt},
      {"role": "user", "content": prompt}
      ]
    )

    return completion.choices[0].message.content

  def llm_response(self, m_uid, text):
    self.gpt_system_prompt = "你是一名擅長分析句子結構的助理"
    self.gpt_prompt = f'''
                      你是一位擅長標註句子的助理，標注類別有:[what,which,when,how,why]，請根據所提供的範例,定義與類別標註句子，不要有額外的解釋，只回覆標註後的句子
                      定義：
                      what:泛指商品類別
                      when:泛指時間段
                      how:泛指消費總額
                      which:泛指需要提取商品
                      why:泛指須將問句相關的資料提取
                      範例：
                      (
                      #我買菸主要花在哪些商品? /
                      我買[菸(what)]主要花在[哪些商品(which)]?
                      #為什麼我上個月的食物支出特別高? /
                      [為什麼(why)]我[上個月(when)]的[食物(what)][支出特別高(which)]?
                      #我上週的飲食支出是多少? /
                      我[上週(when)]的[飲食(what)][支出是多少(how)]?
                      #我本月的飲食消費有哪些? /
                      我[本月(when)]的[飲食(what)][消費有哪些(which)]?
                      #我在其他上的主要支出項目有哪些？/
                      我在[其他(what)]上的主要[支出項目有哪些(which)]？
                      )
                      #{text} /
                      '''
    pos_text = self.gpt(self.gpt_system_prompt, self.gpt_prompt, "gpt-3.5-turbo")
    self.gpt_system_prompt = "你是一名擅長Cypher語法的助理"
    #類別需要導入
    self.gpt_prompt = f'''
                      這是一張圖的節點與邊的定義，你在產生Cypher查詢時可以參考以下圖的節點與邊的定義:
                      Node:
                        Store:包含商店名稱
                        Item:包含商品名稱,商品價格,商品類別
                        Date:包含發票的年,月,日日期
                        Invoice:包含發票的號碼,發票消費總額
                      relation:
                        SELL:Store販賣Item
                        RECEIVE_FROM:Invoice由Store開立
                        PURCHASE:Invoice購買Item,包含數量
                        PURCHASE_DATE:Invoice開立Date

                      這是標註記號的定義:
                        what:泛指商品類別
                        when:泛指時間段
                        how:泛指消費總額
                        which:泛指需要提取商品
                        why:泛指須將問句相關的資料提取

                      類別包含：香菸, 其他, 飲品, 食品

                      你是一名助手，能夠根據以上定義與範例產生Cypher查詢。
                      範例：
                      (
                      #我[上週(when)]的[飲食(what)]支出是[多少(how)]?/
                      MATCH (member:Member {{m_uid: 'askjfsl'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '食品' AND date.year = 2024 AND date.month = 3 AND date.day IN [25,26,27,28,29,30,31]
                      RETURN SUM(item.item_price * p.item_quantity) AS 總計消費, NULL AS 商品, NULL AS 購買數量, NULL AS 年, NULL AS 月, NULL AS 日

                      UNION ALL

                      MATCH (member:Member {{m_uid: 'askjfsl'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '食品' AND date.year = 2024 AND date.month = 3 AND date.day IN [25,26,27,28,29,30,31]
                      RETURN NULL AS 總計消費, item.item_name AS 商品, p.item_quantity AS 購買數量, date.year AS 年, date.month AS 月, date.day AS 日

                      #我買[菸(what)]主要花在[哪些商品(which)]?/
                      MATCH (member:Member {{m_uid: 'slkdmalfm'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '食品'
                      WITH item.item_name AS 商品, COUNT(p) AS 購買次數, SUM(item.item_price * p.item_quantity) AS 總計消費

                      WITH 商品, 購買次數, 總計消費
                      ORDER BY 購買次數 DESC LIMIT 10
                      WITH 商品, 購買次數, 總計消費, '購買次數' AS 排序方式
                      RETURN 商品, 購買次數, 總計消費, 排序方式

                      UNION ALL

                      MATCH (member:Member {{m_uid: 'slkdmalfm'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '食品'
                      WITH item.item_name AS 商品, COUNT(p) AS 購買次數, SUM(item.item_price * p.item_quantity) AS 總計消費
                      ORDER BY 總計消費 DESC LIMIT 10
                      WITH 商品, 購買次數, 總計消費, '消費總額' AS 排序方式
                      RETURN 商品, 購買次數, 總計消費, 排序方式

                      #[為什麼(why)]我[上個月(when)]的[食物(what)][支出特別高(which)]?/
                      MATCH (member:Member {{m_uid: 'casdcfad'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '食品' AND date.year = 2024 AND date.month = 3
                      RETURN item.item_name AS 商品, (item.item_price * p.item_quantity) AS 總計消費, p.item_quantity AS 購買數量, date.year AS 年, date.month AS 月, date.day AS 日
                      ORDER BY 總計消費 DESC LIMIT 20

                      #我的[食品(what)]支出都花在[哪些地方(which)]？
                      MATCH (member:Member {{m_uid: 'asfsaf'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '食品'
                      RETURN DISTINCT item.item_name AS 商品, (item.item_price * p.item_quantity) AS 總計消費

                      #[為什麼(why)]我[這週(when)]的[飲料(what)]支出比[上週(when)][多(how)]？
                      MATCH (member:Member {{m_uid: 'asfasft'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '飲品'
                        AND date.year = 2024
                        AND date.month = 3
                        AND date.day IN [25,26,27,28,29,30,31]
                      WITH SUM(item.item_price * p.item_quantity) AS ThisWeek
                      MATCH (member:Member {{m_uid: 'asfasft'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '飲品'
                        AND date.year = 2024
                        AND date.month = 3
                        AND date.day IN [18,19,20,21,22,23,24]
                      WITH ThisWeek, SUM(item.item_price * p.item_quantity) AS LastWeek
                      RETURN ThisWeek - LastWeek AS 飲品總支出差異, NULL AS 前十較高消費商品, NULL AS 購買數量, NULL AS 商品價格, NULL AS 時間範圍

                      UNION ALL

                      MATCH (member:Member {{m_uid: 'asfasft'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '飲品'
                        AND date.year = 2024
                        AND date.month = 3
                        AND date.day IN [25,26,27,28,29,30,31]
                      RETURN NULL AS 飲品總支出差異, item.item_name AS 前十較高消費商品, p.item_quantity AS 購買數量, item.item_price AS 商品價格, 'ThisWeek' AS 時間範圍 LIMIT 10

                      UNION ALL

                      MATCH (member:Member {{m_uid: 'asfasft'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '飲品'
                        AND date.year = 2024
                        AND date.month = 3
                        AND date.day IN [18,19,20,21,22,23,24]
                      RETURN NULL AS 飲品總支出差異, item.item_name AS 前十較高消費商品, p.item_quantity AS 購買數量, item.item_price AS 商品價格, 'LastWeek' AS 時間範圍 LIMIT 10
                      )

                      除了Cypher查詢之外，請勿回覆任何解釋或任何其他資訊。
                      請使用模糊查詢的方式產生Cypher查詢。
                      您永遠不要為你的不準確回應感到抱歉，並嚴格根據提供的cypher範例產生cypher語句。
                      產生cypher語句時務必注意所提供的今天日期,今天日期為2024/03/31。
                      不要提供任何無法從Cypher範例推斷出的Cypher語句。
                      當由於缺少對話上下文而無法推斷密碼語句時，通知用戶，並說明缺少的上下文是什麼。
                      m_uid為:{m_uid}
                      現在請為這個查詢產生Cypher:
                      #{pos_text}/
                      '''
    self.query = re.sub(r'[`]', '', self.gpt(self.gpt_system_prompt, self.gpt_prompt, 'gpt-4o-2024-05-13')).strip()
    try:
      graph_data = self.graph.run(self.query)
      data = []
      if graph_data:
        for record in graph_data:
          record_dict = dict(record)
          data.append(record_dict)

      df = pd.DataFrame(data)
    except:
      df = pd.DataFrame()

    # check if need image or not 
    self.gpt_system_prompt = "你是一名擅長Cypher語法的助理"
    self.gpt_prompt = f'''
                      這是一張圖的節點與邊的定義，你在產生Cypher查詢時可以參考以下圖的節點與邊的定義:
                      Node:
                        Store:包含商店名稱
                        Item:包含商品名稱,商品價格,商品類別
                        Date:包含發票的年,月,日日期
                        Invoice:包含發票的號碼,發票消費總額
                      relation:
                        SELL:Store販賣Item
                        RECEIVE_FROM:Invoice由Store開立
                        PURCHASE:Invoice購買Item,包含數量
                        PURCHASE_DATE:Invoice開立Date

                      類別包含：香菸, 其他, 飲品, 食品

                      你是一名cypher指令生成助手，請判斷是否需要查詢，判斷條件為能夠產生"消費"欄位，如果能產生消費"欄位,再請根據以上定義與範例產生Cypher查詢，如果不能請回覆Pass。
                      範例：
                      (
                      #我上週的飲食支出是多少?/
                      MATCH (member:Member {{m_uid: 'sjafndpqlsk'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '食品' AND date.year = 2024 AND date.month = 3 AND date.day IN [25,26,27,28,29,30,31]
                      RETURN item.item_name AS 商品, item.item_price * p.item_quantity AS 消費, date.year AS 年, date.month AS 月, date.day AS 日

                      #為什麼我上個月的食物支出特別高?/
                      MATCH (member:Member {{m_uid: 'casdcfad'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '食品' AND date.year = 2024 AND date.month = 2
                      RETURN item.item_name AS 商品, item.item_price * p.item_quantity AS 消費, date.year AS 年, date.month AS 月, date.day AS 日
                      ORDER BY 消費 DESC LIMIT 10

                      #我的食品支出都花在哪些地方?/
                      MATCH (member:Member {{m_uid: 'asfasf'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '食品'
                      RETURN item.item_name AS 商品, item.item_price * p.item_quantity AS 消費, date.year AS 年, date.month AS 月, date.day AS 日
                      ORDER BY 消費 DESC LIMIT 10

                      #為什麼我這週的飲料支出比上週多？/
                      MATCH (member:Member {{m_uid: '98k'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '飲品'
                        AND date.year = 2024
                        AND date.month = 3
                        AND date.day IN [25,26,27,28,29,30,31]
                      RETURN item.item_name AS 商品, item.item_price * p.item_quantity AS 消費, 'ThisWeek' AS 時間範圍 ORDER BY 消費 DESC LIMIT 10

                      UNION ALL

                      MATCH (member:Member {{m_uid: '98k'}})-[:OWN]->(invoice:Invoice)-[:PURCHASE_DATE]->(date:Date)
                      MATCH (invoice)-[p:PURCHASE]->(item:Item)
                      WHERE item.item_category = '飲品'
                        AND date.year = 2024
                        AND date.month = 3
                        AND date.day IN [18,19,20,21,22,23,24]
                      RETURN item.item_name AS 商品, item.item_price * p.item_quantity AS 消費, 'LastWeek' AS 時間範圍 ORDER BY 消費 DESC LIMIT 10

                      #我前天吃了一頓大餐好爽/
                      Pass
                      #我上個月喝了超多奶茶的/
                      Pass
                      )

                      產生查詢時, 除了Cypher查詢之外，請勿回覆任何解釋或任何其他資訊。
                      請使用模糊查詢的方式產生Cypher查詢。
                      您永遠不要為你的不準確回應感到抱歉，並嚴格根據提供的cypher範例產生cypher語句。
                      產生cypher語句時務必注意所提供的今天日期,今天日期為2024/03/31。
                      m_uid為:{m_uid}
                      現在請為這個查詢產生Cypher:
                      #{text}/
                      '''

    self.query = re.sub(r'[`]', '', self.gpt(self.gpt_system_prompt, self.gpt_prompt, 'gpt-4o-2024-05-13')).strip()
    try:
      graph_data = self.graph.run(self.query)
      df_for_image = None
      data = []
      if graph_data:
        for record in graph_data:
          record_dict = dict(record)
          data.append(record_dict)
          
        df_for_image = pd.DataFrame(data)
        self.gen_image = True
      else:
        self.gen_image = False
    except:
      self.gen_image = False

    self.claude_system_prompt = '你是一名財務助理，擅長分析財務支出變化原因'
    self.claude_prompt = f'''
                          請參考列表內容簡短回答用戶的問題, 並回覆與解釋用戶問題的答案，請勿回覆任何其他資訊。
                          請務必注意消費支出的總金額正確與商品數量的正確：
                          列表:
                            {df.to_string()}
                          用戶問題:
                            {text}
                          '''
    response = self.claude(self.claude_system_prompt, self.claude_prompt)

    if self.gen_image:
      return [response, self.gen_image, df_for_image]
    else:
      return [response, self.gen_image]

  def generate_report(self, m_uid, alert_rate=0.3, num_of_avg=2, task='month_alert', alert_cate=None):
    self.task = task
    #任務分開
    if self.task == 'month_alert':
      self.nfa = num_of_avg
      self.generate_query(m_uid)
      result = self.graph.run(self.query)
      filter_result = []
      for record in result:
        filter_result.append([record['category'],record['avg_spending'],record['march_spending'],record['spending_difference']])
      columns = ['類別', f'前{self.nfa}個月平均開銷', '當月開銷', '開銷變化比例']
      self.cost_change_table = pd.DataFrame(filter_result, columns=columns)
      self.alert_category = self.cost_change_table[self.cost_change_table['開銷變化比例']>alert_rate]['類別'].tolist()
      return self.alert_category

    elif self.task == 'analysis_alert':
      self.purchase_table = ''
      self.generate_query(m_uid, ac=alert_cate)
      result = self.graph.run(self.query)

      data = []
      for record in result:
          record_dict = dict(record)
          record_dict['purchase_date'] = f"{record_dict['purchase_year']}{record_dict['purchase_month']:02d}{record_dict['purchase_day']:02d}"
          data.append(record_dict)

      df = pd.DataFrame(data)
      df = df.drop(['purchase_year','purchase_month','purchase_day'], axis=1)
      columns = ['month', '店家', '商品', '商品單價', '購買數量', '總計消費', '購買日期']
      df.columns = columns
      for month in [i for i in range((int(self.today[1])-(self.nfa+1)), int(self.today[1]))]:
        monthly_df = df[df['month'] == month].sort_values('總計消費', ascending=False)[:20]
        self.purchase_table += f'''
                                {month}月份總消費筆數: {len(monthly_df)}筆\n
                                {month}月份前20筆較高消費:\n{monthly_df[['店家', '商品', '商品單價', '購買數量', '總計消費', '購買日期']]}\n
                                {month}月份前20筆較高總消費: {monthly_df['總計消費'].sum()}\n
                              '''
      cate_cost_change = self.cost_change_table[self.cost_change_table['類別']==alert_cate].to_string()
      self.claude_system_prompt = '你是一名財務助理，擅長分析財務支出變化原因'
      self.claude_prompt = f'''
                  以下包含{alert_cate}類別支出變化列表,各月份消費筆數與該類別的前{self.nfa}個月份與當月份類別前20筆較高消費列表,
                  請根據列表內容分析出導致當月{alert_cate}類別支出增加的商品項目, 參考範例回覆一份簡單易懂的結論, 不需要過多的解釋,
                  請務必注意各月份消費支出的總金額正確與商品數量的總和正確：
                  類別支出變化列表:
                    {cate_cost_change}
                  前{self.nfa}個月份與當月份類別前20較高消費列表:
                    {self.purchase_table}
                  範例:
                    結論:
                    導致3月份香菸類別支出大幅增加的主要原因是購買了大量的萬寶路金香菸。相較於前2個月主要購買較便宜的雲絲頓銀香菸，3月份購買了多次萬寶路金香菸(單價110元)，且每次購買數量都在5包以上，導致支出大增。
                  '''
      reason = self.claude(self.claude_system_prompt, self.claude_prompt)
      return reason