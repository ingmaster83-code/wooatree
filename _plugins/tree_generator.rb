require 'json'

module Jekyll
  class TreePageGenerator < Generator
    safe true
    priority :normal

    def generate(site)
      items = load_json(site, '_rawdata/tree.json')

      Jekyll.logger.info "TreeGenerator:", "#{items.size}개 보호수 페이지 생성 중..."
      items.each do |c|
        next if c['slug'].to_s.strip.empty?
        site.pages << TreePage.new(site, c)
      end

      Jekyll.logger.info "TreeGenerator:", "완료 (#{items.size}개)"
    end

    private

    def load_json(site, path)
      file = File.join(site.source, path)
      return [] unless File.exist?(file)
      JSON.parse(File.read(file, encoding: 'utf-8'))
    rescue => e
      Jekyll.logger.warn "TreeGenerator:", "#{path} 로드 실패: #{e.message}"
      []
    end
  end

  class TreePage < Page
    def initialize(site, c)
      @site = site
      @base = site.source
      @dir  = "tree/#{c['slug']}"
      @name = 'index.html'

      self.process(@name)
      self.read_yaml(File.join(@base, '_layouts'), 'tree.html')
      self.data.merge!(c)
      self.data['layout']      = 'tree'
      self.data['title']       = build_title(c)
      self.data['description'] = build_desc(c)
    end

    private

    def build_title(c)
      loc = [c['doShort'], c['sigungu']].compact.join(' ')
      "#{c['treeName']} #{loc} 위치 정보"
    end

    def build_desc(c)
      loc = [c['doShort'], c['sigungu']].compact.join(' ')
      "#{loc} #{c['treeName']}의 위치, 수령, 크기 정보를 확인하세요."[0, 155]
    end
  end
end
