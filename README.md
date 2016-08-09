# Really Basic Site Archive

I'm f***ing tired of people letting valuable content drop because they didn't think to actually implement any sort of sustainability plan. This stupid little docker container takes a site and archives it with the wayback archive.

If you also want to archive something you can


```
git clone https://github.com/seamustuohy/sloppy_archivist
sudo docker build -t sloppy_archivist .
sudo docker run -v $HOME/temp/scrapy_Docker:/etc/spider -e URL='http://domain.domain.TLD/everything/else' sloppy_archivist
```
