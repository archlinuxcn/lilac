class Options(dict):

    def __getitem__(self, key):
        if not key in self.keys():
            self.__setitem__(key, Options())
        return super().__getitem__(key)

    def __getattr__(self, attr):
        if not attr in self.keys():
            self[attr] = Options()
        return self[attr]

    def __setattr__(self, attr, value):
        self[attr] = value

    def __delattr__(self, attr):
        del self[attr]

if __name__ == '__main__':
    import json

    config = Options()
    config.test = 'test'
    config['test2'] = 'test2'
    print(config)
    config['test'] = 'test2'
    config.test2 = 'test'
    print(config)
    del config.test
    print(config)
    del config['test2']
    print(config)
    config.test.test = 'test'
    config['test2'].test2 = 'test2'
    print(config)
    config.test['test'] = 'test2'
    config['test2']['test2'] = 'test'
    print(config)
    print(json.dumps(config))
