# coding=utf-8
import torch
import numpy as np


# Vocab: 词典，由两部分组成
# Part 1: 固定词典部分，由数据集常见词构成，word embedding为预训练的或随机初始化的
# Part 2: 可变词典部分，copy机制需要实现一个动态词表，这一部分由出现在batch src中但没有出现在固定词典中的词构成，
#         每读取一个batch，都要重新更改可变词典部分
class Vocab:
    def __init__(self, args, embed=None):
        self.args = args
        self.embed = []
        self.PAD_IDX = 0
        self.SOS_IDX = 1
        self.EOS_IDX = 2
        self.UNK_IDX = 3
        self.PAD_TOKEN = '<PAD>'
        self.SOS_TOKEN = '<SOS>'
        self.EOS_TOKEN = '<EOS>'
        self.UNK_TOKEN = '<UNK>'
        self.word_num = 4   # 词表总大小，包括固定部分和可变部分
        self.fixed_num = 4  # 固定部分大小
        self.word2id = {self.PAD_TOKEN: self.PAD_IDX, self.SOS_TOKEN: self.SOS_IDX, self.EOS_TOKEN: self.EOS_IDX,
                        self.UNK_TOKEN: self.UNK_IDX}
        self.id2word = {v: k for k, v in self.word2id.items()}
        self.word2cnt = {self.PAD_TOKEN: 10000, self.SOS_TOKEN: 10000, self.EOS_TOKEN: 10000,
                         self.UNK_TOKEN: 10000}  # 给这几个标记较大的值防止后面被删去
        self.user_num = 1
        self.user2id = {'<UNK-USER>': 0}
        self.id2user = {0: '<UNK-USER>'}
        self.product_num = 1
        self.product2id = {'<UNK-PRODUCT>': 0}
        self.id2product = {0: '<UNK-PRODUCT>'}
        for i in range(4):
            self.embed.append(np.random.normal(size=args.embed_dim))
        if embed is not None:
            for w in sorted(embed.keys()):
                if w not in self.word2id:
                    self.word2id[w] = self.word_num
                    self.id2word[self.word_num] = w
                    self.word2cnt[w] = 0
                    self.embed.append(embed[w])
                    self.word_num += 1
        self.fixed_num = self.word_num

    # 读取一个句子，更新词表以及相关记录
    def add_sentence(self, sent):
        for w in sent:
            if w not in self.word2id:
                self.word2id[w] = self.word_num
                self.id2word[self.word_num] = w
                self.word2cnt[w] = 1
                self.embed.append(np.random.normal(size=self.args.embed_dim))
                self.word_num += 1
            else:
                self.word2cnt[w] += 1
        self.fixed_num = self.word_num

    # 读取一个用户，更新用户列表
    def add_user(self, user):
        if user not in self.user2id:
            self.user2id[user] = self.user_num
            self.id2user[self.user_num] = user
            self.user_num += 1

    # 读取一个产品，更新产品列表
    def add_product(self, product):
        if product not in self.product2id:
            self.product2id[product] = self.product_num
            self.id2product[self.product_num] = product
            self.product_num += 1

    # 已经读完了所有句子，对词表进行剪枝，只保留出现次数大于等于self.args.word_min_cnt的词以及相应词向量
    def trim(self):
        print('original vocab size: %d' % len(self.word2cnt))
        reserved_words, reserved_idx = [], []
        for i in range(self.word_num):
            w = self.id2word[i]
            if self.word2cnt[w] >= self.args.word_min_cnt:
                reserved_words.append(w)
                reserved_idx.append(i)
        cnt = 0
        word2id, id2word, word2cnt = {}, {}, {}
        embed = []
        for w in reserved_words:
            word2id[w] = cnt
            id2word[cnt] = w
            word2cnt[w] = self.word2cnt[w]
            cnt += 1
        for i in reserved_idx:
            embed.append(self.embed[i])
        self.word_num = cnt
        self.fixed_num = cnt
        assert len(word2id) == len(id2word) and len(id2word) == len(word2cnt) and len(word2cnt) == len(embed)
        self.word2id, self.id2word, self.word2cnt, self.embed = word2id, id2word, word2cnt, embed
        print('Vocab size: %d' % len(self.word2id))
        embed = torch.FloatTensor(embed)
        if self.args.use_cuda:
            embed = embed.cuda()
        return embed

    def word_id(self, w):
        if w in self.word2id:
            return self.word2id[w]
        return self.UNK_IDX

    def id_word(self, idx):
        assert 0 <= idx < self.word_num
        return self.id2word[idx]

    # 给定一个batch的文本数据，删除上一个batch的可变词典部分，生成该batch的可变词典；
    # 同时，生成神经网络所需要的input tensors
    def read_batch(self, batch):
        # 删除上一个batch的可变词典部分，可变词典部分没有embedding，不记录word_cnt
        for i in range(self.fixed_num, self.word_num):
            w = self.id_word(i)
            self.id2word.pop(i)
            self.word2id.pop(w)
        self.word_num = self.fixed_num

        # 存储评论和摘要的文本，便于valid时查看效果，按照评论长度由大到小排序
        src_text, trg_text = [], []
        for review, summary in zip(batch['reviewText'], batch['summary']):
            src_text.append(review)
            trg_text.append(summary)
        idx = list(range(len(batch['summary'])))  # 将一个batch中的数据由长到短排序，方便作为GRU输入
        idx.sort(key=lambda k: len(src_text[k].split()), reverse=True)
        src_text = [src_text[i] for i in idx]
        trg_text = [trg_text[i] for i in idx]

        # 生成该batch的可变词典部分
        for review in src_text:
            review = review.split()
            for w in review:
                if w not in self.word2id:
                    self.word2id[w] = self.word_num
                    self.id2word[self.word_num] = w
                    self.word_num += 1

        # 生成神经网络所需要的input tensors
        src_max_len = len(src_text[0].split())
        trg_max_len = self.args.sum_max_len
        src, trg, src_mask, src_lens, trg_lens = [], [], [], [], []
        src_embed, trg_embed = [], []  # 针对embed的src和trg输入，与src和trg相比，将处于可变词典的词序号替换成UNK_IDX
        for review in src_text:
            review = review.split()[:src_max_len]
            cur_idx = []
            for w in review:
                cur_idx.append(self.word_id(w))
            cur_idx.extend([self.PAD_IDX] * (src_max_len - len(review)))
            src.append(cur_idx)
            src_embed.append([i if i < self.fixed_num else self.UNK_IDX for i in cur_idx])
            src_mask.append([1] * len(review) + [0] * (src_max_len - len(review)))
            src_lens.append(len(review))
        for i, summary in enumerate(trg_text):
            summary = summary.split() + [self.EOS_TOKEN]
            summary = summary[:trg_max_len]
            cur_idx = []
            for w in summary:
                cur_id = self.word_id(w)
                if cur_id >= self.fixed_num and cur_id not in src[i]:
                    cur_id = self.UNK_IDX
                cur_idx.append(cur_id)
            cur_idx.extend([self.PAD_IDX] * (trg_max_len - len(summary)))
            trg.append(cur_idx)
            trg_embed.append([i if i < self.fixed_num else self.UNK_IDX for i in cur_idx])
            trg_lens.append(len(summary))

        src_user, src_product = [], []
        for user in batch['userID']:
            if user in self.user2id:
                src_user.append(self.user2id[user])
            else:
                src_user.append(0)
        for product in batch['productID']:
            if product in self.product2id:
                src_product.append(self.product2id[product])
            else:
                src_product.append(0)

        src, trg, src_mask = torch.LongTensor(src), torch.LongTensor(trg), torch.LongTensor(src_mask)
        src_embed, trg_embed = torch.LongTensor(src_embed), torch.LongTensor(trg_embed)
        src_user, src_product = torch.LongTensor(src_user), torch.LongTensor(src_product)
        if self.args.use_cuda:
            src, trg, src_mask = src.cuda(), trg.cuda(), src_mask.cuda()
            src_embed, trg_embed = src_embed.cuda(), trg_embed.cuda()
            src_user, src_product = src_user.cuda(), src_product.cuda()

        return src, trg, src_embed, trg_embed, src_user, src_product, src_mask, src_lens, trg_lens, src_text, trg_text